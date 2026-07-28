import os
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from screener.modules.backtest import (
    BacktestExitReason,
    BacktestRepository,
    BacktestRun,
    BacktestService,
    BacktestStatus,
    BacktestTrade,
    DatabaseBacktestExecutor,
    WatchlistEntryStrategy,
)
from screener.modules.backtest.models import BacktestRunRecord, BacktestTradeRecord
from screener.modules.market.infrastructure.models import DailyBarRecord, Stock
from screener.modules.market.watchlist.models import WatchlistEntryRecord

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL PostgreSQL database is required"
)


@pytest.fixture
async def session() -> AsyncSession:
    url = os.environ["TEST_DATABASE_URL"]
    if not url.startswith("postgresql+asyncpg://"):
        pytest.fail("TEST_DATABASE_URL must use postgresql+asyncpg")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as value:
        for model in (
            BacktestTradeRecord,
            BacktestRunRecord,
            WatchlistEntryRecord,
            DailyBarRecord,
            Stock,
        ):
            await value.execute(delete(model))
        await value.commit()
        yield value
        await value.rollback()
        for model in (
            BacktestTradeRecord,
            BacktestRunRecord,
            WatchlistEntryRecord,
            DailyBarRecord,
            Stock,
        ):
            await value.execute(delete(model))
        await value.commit()
    await engine.dispose()


def new_run() -> BacktestRun:
    return BacktestRun.create(
        "watchlist_entry",
        date(2026, 1, 1),
        date(2026, 1, 10),
        "1",
        {},
        datetime(2026, 1, 11, tzinfo=UTC),
    )


def trade(run_id: UUID, trade_id: UUID | None = None) -> BacktestTradeRecord:
    return BacktestTradeRecord(
        id=trade_id or uuid4(),
        run_id=run_id,
        symbol="005930",
        signal_date=date(2026, 1, 2),
        entry_date=date(2026, 1, 3),
        entry_price=Decimal("12345.67890123"),
        quantity=17,
        exit_date=date(2026, 1, 5),
        exit_price=Decimal("12789.12345678"),
        exit_reason=BacktestExitReason.TAKE_PROFIT,
        gross_pnl=Decimal("7538.55544435"),
        commission=Decimal("64.94851848"),
        tax=Decimal("326.12264815"),
        slippage_cost=Decimal("41.23456789"),
        net_pnl=Decimal("7147.48427772"),
        holding_days=2,
    )


async def seed_execution_data(session: AsyncSession) -> None:
    session.add(Stock(symbol="005930", name="Samsung", market="KOSPI"))
    session.add(
        WatchlistEntryRecord(
            trading_date=date(2026, 1, 2),
            symbol="005930",
            rank=1,
            total_score="1",
            component_scores="{}",
            warnings="[]",
            snapshot="{}",
        )
    )
    bars = [
        (date(2026, 1, 2), "100", "101", "99", "100"),
        (date(2026, 1, 3), "100", "102", "99", "101"),
        (date(2026, 1, 4), "101", "120", "100", "115"),
        # A catastrophic price outside the requested range proves it is never loaded.
        (date(2026, 1, 11), "1", "1", "1", "1"),
    ]
    for trading_date, opening, high, low, close in bars:
        session.add(
            DailyBarRecord(
                symbol="005930",
                trading_date=trading_date,
                open=Decimal(opening),
                high=Decimal(high),
                low=Decimal(low),
                close=Decimal(close),
                volume=1000,
                source="test",
            )
        )
    await session.flush()


async def test_trade_and_exact_decimals_survive_round_trip(session: AsyncSession) -> None:
    original = new_run().start().fail("provider unavailable", "MARKET_DATA_UNAVAILABLE")
    repository = BacktestRepository(session)
    await repository.save(original)
    session.add(trade(original.id))
    await session.commit()
    restored = await repository.get(original.id)
    actual = (await repository.list_trades(original.id))[0]
    assert restored == original
    assert isinstance(actual, BacktestTrade)
    assert actual.entry_price == Decimal("12345.67890123")
    assert actual.exit_price == Decimal("12789.12345678")
    assert actual.gross_pnl == Decimal("7538.55544435")
    assert actual.commission == Decimal("64.94851848")
    assert actual.tax == Decimal("326.12264815")
    assert actual.slippage_cost == Decimal("41.23456789")
    assert actual.net_pnl == Decimal("7147.48427772")


async def test_deleting_run_cascades_to_trades(session: AsyncSession) -> None:
    original = new_run()
    await BacktestRepository(session).save(original)
    session.add(trade(original.id))
    await session.commit()
    await session.delete(await session.get_one(BacktestRunRecord, original.id))
    await session.commit()
    assert await session.scalar(select(func.count()).select_from(BacktestTradeRecord)) == 0


async def test_duplicate_run_symbol_signal_date_violates_unique_constraint(
    session: AsyncSession,
) -> None:
    original = new_run()
    await BacktestRepository(session).save(original)
    session.add_all([trade(original.id), trade(original.id)])
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_full_executor_persists_bounded_trade_and_metrics(session: AsyncSession) -> None:
    await seed_execution_data(session)
    service = BacktestService(
        BacktestRepository(session),
        DatabaseBacktestExecutor(session, WatchlistEntryStrategy(session)),
        30,
    )
    completed = await service.create("watchlist_entry", date(2026, 1, 1), date(2026, 1, 10), "1")
    await session.commit()
    persisted = await BacktestRepository(session).get(completed.id)
    trades = await BacktestRepository(session).list_trades(completed.id)
    assert persisted is not None and persisted.status is BacktestStatus.COMPLETED
    assert persisted.result is not None and persisted.result["entered_trades"] == 1
    assert persisted.result["total_signals"] == 1
    assert len(trades) == 1
    assert trades[0].entry_date > trades[0].signal_date
    assert trades[0].exit_date <= completed.end_date
    assert trades[0].exit_reason is BacktestExitReason.TAKE_PROFIT


async def test_constraint_failure_marks_failed_and_leaves_session_usable(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed_execution_data(session)
    collision_id = uuid4()
    unrelated = new_run()
    await BacktestRepository(session).save(unrelated)
    session.add(trade(unrelated.id, collision_id))
    await session.flush()
    monkeypatch.setattr("screener.modules.backtest.executor.uuid4", lambda: collision_id)
    service = BacktestService(
        BacktestRepository(session),
        DatabaseBacktestExecutor(session, WatchlistEntryStrategy(session)),
        30,
    )
    failed = await service.create("watchlist_entry", date(2026, 1, 1), date(2026, 1, 10), "1")
    await session.commit()
    persisted = await BacktestRepository(session).get(failed.id)
    assert persisted is not None and persisted.status is BacktestStatus.FAILED
    assert persisted.failure_code == "EXECUTION_FAILED"
    assert persisted.failure_message and "backtest_trades_pkey" in persisted.failure_message
    assert await session.scalar(select(func.count()).select_from(BacktestTradeRecord)) == 1
    assert (await session.execute(select(1))).scalar_one() == 1
