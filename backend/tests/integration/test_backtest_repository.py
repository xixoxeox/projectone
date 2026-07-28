import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from screener.modules.backtest import (
    BacktestExitReason,
    BacktestRepository,
    BacktestRun,
    DatabaseBacktestExecutor,
    WatchlistEntryStrategy,
)
from screener.modules.backtest.models import BacktestRunRecord, BacktestTradeRecord
from screener.modules.backtest.service import BacktestService
from screener.modules.backtest.strategy import BacktestSignal
from screener.modules.market.infrastructure.models import DailyBarRecord, Stock
from screener.modules.market.ranking import RankedCandidate
from screener.modules.market.screening import ScreeningResult
from screener.modules.market.watchlist import WatchlistRepository

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL PostgreSQL database is required"
)
TRUNCATE_TEST_DATA = (
    "TRUNCATE backtest_trades, backtest_runs, watchlist_entries, daily_bars, stocks CASCADE"
)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    url = os.environ["TEST_DATABASE_URL"]
    assert url.startswith("postgresql+asyncpg://"), "integration tests require PostgreSQL"
    assert url != os.getenv("PRODUCTION_DATABASE_URL"), "test database must not be production"
    assert (make_url(url).database or "").endswith("_test"), (
        "refusing destructive integration-test cleanup outside a *_test database"
    )
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as value:
        await value.execute(text(TRUNCATE_TEST_DATA))
        await value.commit()
        yield value
        await value.rollback()
        await value.execute(text(TRUNCATE_TEST_DATA))
        await value.commit()
    await engine.dispose()


def run() -> BacktestRun:
    return BacktestRun.create(
        "watchlist_entry",
        date(2026, 1, 1),
        date(2026, 1, 20),
        "1",
        {"position_size": "1000.12345678"},
        datetime(2026, 1, 21, 12, 30, tzinfo=UTC),
    )


def trade_record(run_id: UUID, **changes: object) -> BacktestTradeRecord:
    values = {
        "id": uuid4(),
        "run_id": run_id,
        "symbol": "005930",
        "signal_date": date(2026, 1, 2),
        "entry_date": date(2026, 1, 3),
        "entry_price": Decimal("123.12345678"),
        "quantity": 7,
        "exit_date": date(2026, 1, 5),
        "exit_price": Decimal("130.87654321"),
        "exit_reason": BacktestExitReason.TAKE_PROFIT,
        "gross_pnl": Decimal("54.27360401"),
        "commission": Decimal("0.26600000"),
        "tax": Decimal("1.37420370"),
        "slippage_cost": Decimal("0.14000000"),
        "net_pnl": Decimal("52.63340031"),
        "holding_days": 2,
    }
    values.update(changes)
    return BacktestTradeRecord(**values)


async def test_run_metadata_and_trade_round_trip_with_exact_decimals(session: AsyncSession) -> None:
    original = run().start().complete({"net_profit": "52.63340031"})
    repository = BacktestRepository(session)
    await repository.save(original)
    record = trade_record(original.id)
    session.add(record)
    await session.commit()
    session.expunge_all()

    assert await repository.get(original.id) == original
    restored = (await repository.list_trades(original.id))[0]
    assert restored.entry_price == Decimal("123.12345678")
    assert restored.exit_price == Decimal("130.87654321")
    assert restored.net_pnl == Decimal("52.63340031")
    assert restored.exit_reason is BacktestExitReason.TAKE_PROFIT


async def test_trade_cascade_delete(session: AsyncSession) -> None:
    original = run()
    await BacktestRepository(session).save(original)
    session.add(trade_record(original.id))
    await session.commit()
    await session.execute(delete(BacktestRunRecord).where(BacktestRunRecord.id == original.id))
    await session.commit()
    assert await session.scalar(select(func.count()).select_from(BacktestTradeRecord)) == 0


async def test_duplicate_signal_unique_constraint(session: AsyncSession) -> None:
    original = run()
    await BacktestRepository(session).save(original)
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add_all([trade_record(original.id), trade_record(original.id)])
            await session.flush()
    assert await session.scalar(select(func.count()).select_from(BacktestRunRecord)) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"signal_date": date(2026, 1, 3), "entry_date": date(2026, 1, 3)},
        {"entry_date": date(2026, 1, 5), "exit_date": date(2026, 1, 4)},
        {"quantity": 0},
    ],
)
async def test_trade_date_and_quantity_constraints(
    session: AsyncSession, changes: dict[str, object]
) -> None:
    original = run()
    await BacktestRepository(session).save(original)
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(trade_record(original.id, **changes))
            await session.flush()
    assert await session.scalar(select(func.count()).select_from(BacktestRunRecord)) == 1


async def seed_execution(session: AsyncSession) -> None:
    session.add(
        Stock(
            symbol="005930",
            name="Samsung Electronics",
            market="KOSPI",
            exchange="XKRX",
            currency="KRW",
            country="KR",
            security_type="common_stock",
            listing_status="listed",
            is_active=True,
        )
    )
    await WatchlistRepository(session).save(
        date(2026, 1, 2),
        [
            RankedCandidate(
                symbol="005930",
                rank=1,
                total_score=Decimal("91.25000000"),
                component_scores={"trend": Decimal("91.25000000")},
                source_result=ScreeningResult(
                    symbol="005930",
                    passed=True,
                    reasons=["PASSED: seeded integration candidate"],
                    warnings=[],
                    metrics={"close": Decimal("92.00000000")},
                ),
                warnings=[],
            )
        ],
    )
    for trading_date, opening, high, close in [
        (date(2026, 1, 2), "90", "95", "92"),
        (date(2026, 1, 3), "100", "103", "102"),
        (date(2026, 1, 4), "102", "120", "118"),
        (date(2026, 1, 21), "1", "1", "1"),
    ]:
        session.add(
            DailyBarRecord(
                symbol="005930",
                trading_date=trading_date,
                open=Decimal(opening),
                high=Decimal(high),
                low=Decimal(opening),
                close=Decimal(close),
                volume=100,
                source="test",
                provider_timestamp=datetime(2026, 1, 22, tzinfo=UTC),
            )
        )
    await session.flush()


async def test_full_seeded_execution_persists_next_bar_trade_and_metrics(
    session: AsyncSession,
) -> None:
    await seed_execution(session)
    repository = BacktestRepository(session)
    service = BacktestService(
        repository, DatabaseBacktestExecutor(session, WatchlistEntryStrategy(session)), 30
    )
    completed = await service.create(
        "watchlist_entry",
        date(2026, 1, 1),
        date(2026, 1, 20),
        "1",
        {"position_size": "1000", "slippage_rate": "0"},
    )
    await session.commit()
    trades = await repository.list_trades(completed.id)
    assert completed.status.value == "completed"
    assert completed.result is not None and completed.result["entered_trades"] == 1
    assert len(trades) == 1
    assert trades[0].entry_date == date(2026, 1, 3)  # signal bar is never the entry bar
    assert trades[0].exit_date == date(2026, 1, 4)  # the Jan 21 bar is outside run.end_date


class DuplicateSignalStrategy(WatchlistEntryStrategy):
    async def generate_signals(self, run: BacktestRun) -> list[BacktestSignal]:
        signals = await super().generate_signals(run)
        return [*signals, *signals]


async def test_real_nested_flush_failure_persists_failed_run_and_keeps_session_usable(
    session: AsyncSession,
) -> None:
    await seed_execution(session)
    repository = BacktestRepository(session)
    service = BacktestService(
        repository, DatabaseBacktestExecutor(session, DuplicateSignalStrategy(session)), 30
    )
    failed = await service.create(
        "watchlist_entry",
        date(2026, 1, 1),
        date(2026, 1, 20),
        "1",
        {"position_size": "1000", "slippage_rate": "0"},
    )
    await session.commit()
    session.expunge_all()
    restored = await repository.get(failed.id)
    assert restored is not None and restored.status.value == "failed"
    assert restored.failure_code == "EXECUTION_FAILED"
    assert restored.failure_message is not None
    assert "uq_backtest_trade_signal" in restored.failure_message
    assert await session.scalar(select(func.count()).select_from(BacktestTradeRecord)) == 0
    assert await session.scalar(select(func.count()).select_from(BacktestRunRecord)) == 1
