import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
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


async def test_analysis_repository_uses_canonical_exit_symbol_uuid_order(
    session: AsyncSession,
) -> None:
    completed = run().start().complete({})
    repository = BacktestRepository(session)
    await repository.save(completed)
    same_exit = date(2026, 2, 10)
    session.add_all(
        [
            trade_record(
                completed.id,
                id=UUID(int=9),
                symbol="AAA",
                signal_date=date(2026, 1, 4),
                entry_date=date(2026, 2, 1),
                exit_date=date(2026, 2, 11),
            ),
            trade_record(
                completed.id,
                id=UUID(int=3),
                symbol="BBB",
                signal_date=date(2026, 1, 3),
                entry_date=date(2026, 2, 1),
                exit_date=same_exit,
            ),
            trade_record(
                completed.id,
                id=UUID(int=2),
                symbol="AAA",
                signal_date=date(2026, 1, 2),
                entry_date=date(2026, 2, 1),
                exit_date=same_exit,
            ),
            trade_record(
                completed.id,
                id=UUID(int=1),
                symbol="AAA",
                signal_date=date(2026, 1, 1),
                entry_date=date(2026, 2, 1),
                exit_date=same_exit,
            ),
        ]
    )
    await session.commit()
    restored = await repository.list_all_trades_for_analysis(completed.id)
    assert [item.id.int for item in restored] == [1, 2, 3, 9]
    assert restored[0].net_pnl == Decimal("52.63340031")


async def test_completed_analysis_has_no_500_trade_limit(session: AsyncSession) -> None:
    completed = run().start().complete({})
    repository = BacktestRepository(session)
    await repository.save(completed)
    base = date(2020, 1, 1)
    session.add_all(
        [
            trade_record(
                completed.id,
                id=UUID(int=index + 1),
                symbol="BULK",
                signal_date=base + timedelta(days=index),
                entry_date=base + timedelta(days=index + 1),
                exit_date=base + timedelta(days=index + 2),
                net_pnl=Decimal("0.00000001"),
            )
            for index in range(501)
        ]
    )
    await session.commit()
    service = BacktestService(
        repository, DatabaseBacktestExecutor(session, WatchlistEntryStrategy(session)), 30
    )
    analysis = await service.analyze(completed.id)
    assert analysis.trade_count == 501
    assert analysis.summary.net_profit == Decimal("0.00000501")
    assert len(analysis.cumulative_realized_pnl) == 501
    assert analysis.cumulative_realized_pnl[-1].cumulative_net_pnl == Decimal("0.00000501")


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


class StaticStrategy:
    name = "watchlist_entry"
    version = "1"

    def __init__(self, signals: list[BacktestSignal]) -> None:
        self.signals = signals

    async def generate_signals(self, run: BacktestRun) -> list[BacktestSignal]:
        return self.signals


def portfolio_run(start: date, end: date) -> BacktestRun:
    return BacktestRun.create(
        "watchlist_entry",
        start,
        end,
        "1",
        {
            "execution_mode": "portfolio",
            "initial_capital": "10000",
            "max_open_positions": 3,
            "position_sizing_mode": "fixed_fraction",
            "position_size_pct": "0.25",
            "minimum_cash_buffer_pct": "0",
            "commission_rate": "0",
            "sell_tax_rate": "0",
            "slippage_rate": "0",
            "stop_loss_pct": "0.9",
            "take_profit_pct": "9",
            "max_holding_days": 20,
        },
    )


async def seed_bars(
    session: AsyncSession, symbols: list[str], rows: list[tuple[date, str, str]]
) -> None:
    for symbol in symbols:
        session.add(
            Stock(
                symbol=symbol,
                name=symbol,
                market="KOSPI",
                exchange="XKRX",
                currency="KRW",
                country="KR",
                security_type="common_stock",
                listing_status="listed",
                is_active=True,
            )
        )
        for day, opening, close in rows:
            session.add(
                DailyBarRecord(
                    symbol=symbol,
                    trading_date=day,
                    open=Decimal(opening),
                    high=Decimal(opening),
                    low=Decimal(opening),
                    close=Decimal(close),
                    volume=100,
                    source="test_fixture",
                )
            )
    await session.flush()


async def test_zero_signal_portfolio_persists_canonical_all_cash_calendar(
    session: AsyncSession,
) -> None:
    days = [(date(2026, 1, 2), "10", "11"), (date(2026, 1, 5), "11", "12")]
    await seed_bars(session, ["CAL"], days)
    candidate = portfolio_run(days[0][0], days[-1][0]).start()
    repository = BacktestRepository(session)
    await repository.save(candidate)
    result = await DatabaseBacktestExecutor(session, StaticStrategy([])).execute(candidate)
    completed = candidate.complete(result.metrics)
    await repository.save(completed)
    await session.commit()
    snapshots = await repository.list_portfolio_snapshots(candidate.id)
    assert [item.trading_date for item in snapshots] == [row[0] for row in days]
    for item in snapshots:
        assert (
            item.cash,
            item.market_value,
            item.realized_pnl,
            item.unrealized_pnl,
            item.total_equity,
        ) == (
            Decimal("10000.00000000"),
            Decimal("0E-8"),
            Decimal("0E-8"),
            Decimal("0E-8"),
            Decimal("10000.00000000"),
        )
        assert item.cumulative_return == item.drawdown == item.drawdown_pct == Decimal("0E-8")
        assert item.open_position_count == 0


async def test_no_close_lookahead_and_final_day_signal_is_traded(session: AsyncSession) -> None:
    days = [
        (date(2026, 1, 2), "10", "10"),
        (date(2026, 1, 5), "10", "10"),
        (date(2026, 1, 6), "10", "1000"),
        (date(2026, 1, 7), "10", "10"),
    ]
    await seed_bars(session, ["AAA", "BBB"], days)
    signals = [
        BacktestSignal("AAA", date(2026, 1, 2)),
        BacktestSignal("BBB", date(2026, 1, 5)),
        BacktestSignal("AAA", date(2026, 1, 6)),
    ]
    candidate = portfolio_run(days[0][0], days[-1][0]).start()
    repository = BacktestRepository(session)
    await repository.save(candidate)
    result = await DatabaseBacktestExecutor(session, StaticStrategy(signals)).execute(candidate)
    trades = await repository.list_trades(candidate.id, 100, 0)
    bbb = next(item for item in trades if item.symbol == "BBB")
    assert bbb.quantity == 250  # prior-close equity 10,000 × 25% / 10, not AAA's future close
    assert any(
        item.signal_date == date(2026, 1, 6)
        and item.exit_reason is BacktestExitReason.END_OF_PERIOD
        for item in trades
    )
    assert (
        result.metrics["total_signals"]
        == result.metrics["entered_trades"] + result.metrics["skipped_signals"]
    )
    final = (await repository.list_portfolio_snapshots(candidate.id))[-1]
    assert final.total_equity == Decimal(result.metrics["final_cash"])
    assert final.unrealized_pnl == Decimal("0E-8") and final.open_position_count == 0
