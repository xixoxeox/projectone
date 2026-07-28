import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from screener.modules.backtest import (
    BacktestExecutionResult,
    BacktestExitReason,
    BacktestRepository,
    BacktestRun,
    BacktestService,
    BacktestStatus,
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
        await value.execute(delete(BacktestTradeRecord))
        await value.execute(delete(BacktestRunRecord))
        await value.execute(delete(WatchlistEntryRecord))
        await value.execute(delete(DailyBarRecord))
        await value.execute(delete(Stock))
        await value.commit()
        yield value
        await value.rollback()
    await engine.dispose()


def trade_record(run_id: object, *, symbol: str = "005930") -> BacktestTradeRecord:
    return BacktestTradeRecord(
        id=uuid4(),
        run_id=run_id,
        symbol=symbol,
        signal_date=date(2026, 1, 2),
        entry_date=date(2026, 1, 3),
        entry_price=Decimal("100.12345678"),
        quantity=17,
        exit_date=date(2026, 1, 6),
        exit_price=Decimal("109.87654321"),
        exit_reason=BacktestExitReason.TAKE_PROFIT,
        gross_pnl=Decimal("165.80246931"),
        commission=Decimal("0.53571428"),
        tax=Decimal("2.80185185"),
        slippage_cost=Decimal("3.57000000"),
        net_pnl=Decimal("162.46490318"),
        holding_days=1,
    )


async def persisted_run(session: AsyncSession) -> BacktestRun:
    run = BacktestRun.create("watchlist_entry", date(2026, 1, 1), date(2026, 1, 10), "1")
    await BacktestRepository(session).save(run)
    return run


async def test_trade_round_trip_preserves_decimal_values_exactly(session: AsyncSession) -> None:
    run = await persisted_run(session)
    original = trade_record(run.id)
    session.add(original)
    await session.commit()
    session.expunge_all()

    restored = await session.get(BacktestTradeRecord, original.id)
    assert restored is not None
    assert restored.symbol == "005930"
    assert restored.exit_reason is BacktestExitReason.TAKE_PROFIT
    assert restored.entry_price == Decimal("100.12345678")
    assert restored.exit_price == Decimal("109.87654321")
    assert restored.net_pnl == Decimal("162.46490318")


async def test_deleting_run_cascades_to_trades(session: AsyncSession) -> None:
    run = await persisted_run(session)
    session.add(trade_record(run.id))
    await session.commit()

    await session.execute(delete(BacktestRunRecord).where(BacktestRunRecord.id == run.id))
    await session.commit()
    count = await session.scalar(
        select(func.count())
        .select_from(BacktestTradeRecord)
        .where(BacktestTradeRecord.run_id == run.id)
    )
    assert count == 0


async def test_duplicate_simulated_signal_violates_unique_constraint(
    session: AsyncSession,
) -> None:
    run = await persisted_run(session)
    session.add_all([trade_record(run.id), trade_record(run.id)])
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def seed_market_data(session: AsyncSession) -> None:
    session.add(Stock(symbol="005930", name="Samsung", market="KOSPI"))
    for trading_date, values in (
        (date(2026, 1, 1), (100, 101, 99, 100)),
        (date(2026, 1, 2), (100, 103, 99, 102)),
        (date(2026, 1, 3), (102, 104, 101, 103)),
        # This extreme post-period bar must never affect the simulated exit.
        (date(2026, 1, 6), (1000, 1000, 1, 1000)),
    ):
        open_, high, low, close = values
        session.add(
            DailyBarRecord(
                symbol="005930",
                trading_date=trading_date,
                open=Decimal(open_),
                high=Decimal(high),
                low=Decimal(low),
                close=Decimal(close),
                volume=1000,
                source="test",
            )
        )
    session.add(
        WatchlistEntryRecord(
            trading_date=date(2026, 1, 1),
            symbol="005930",
            rank=1,
            total_score="1",
            component_scores="{}",
            warnings="[]",
            snapshot="{}",
        )
    )
    await session.flush()


async def test_full_executor_persists_trade_and_metrics_without_future_bars(
    session: AsyncSession,
) -> None:
    await seed_market_data(session)
    service = BacktestService(
        BacktestRepository(session),
        DatabaseBacktestExecutor(session, WatchlistEntryStrategy(session)),
        30,
    )
    run = await service.create(
        "watchlist_entry",
        date(2026, 1, 1),
        date(2026, 1, 3),
        "1",
        {"stop_loss_pct": "0.5", "take_profit_pct": "5"},
    )
    await session.commit()

    assert run.status is BacktestStatus.COMPLETED
    assert run.result is not None
    assert run.result["entered_trades"] == 1
    assert run.result["total_signals"] == 1
    trades = await BacktestRepository(session).list_trades(run.id)
    assert len(trades) == 1
    assert trades[0].signal_date < trades[0].entry_date
    assert trades[0].exit_date == date(2026, 1, 3)
    assert trades[0].exit_price < Decimal("1000")


class DuplicateTradeExecutor:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def execute(self, run: BacktestRun) -> BacktestExecutionResult:
        self.session.add_all([trade_record(run.id), trade_record(run.id)])
        await self.session.flush()
        return BacktestExecutionResult({"entered_trades": 2})


async def test_trade_flush_failure_persists_failed_run_and_session_remains_usable(
    session: AsyncSession,
) -> None:
    service = BacktestService(
        BacktestRepository(session),
        DuplicateTradeExecutor(session),
        30,  # type: ignore[arg-type]
    )
    run = await service.create("watchlist_entry", date(2026, 1, 1), date(2026, 1, 10))
    await session.commit()
    session.expunge_all()

    restored = await BacktestRepository(session).get(run.id)
    assert restored is not None
    assert restored.status is BacktestStatus.FAILED
    assert restored.failure_code == "EXECUTION_FAILED"
    assert restored.failure_message
    assert await session.scalar(select(func.count()).select_from(BacktestRunRecord)) == 1
    assert await session.scalar(select(func.count()).select_from(BacktestTradeRecord)) == 0
