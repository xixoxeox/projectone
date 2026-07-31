"""Focused regression tests for the normal and reanalysis orchestration paths."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from screener.modules.market.indicators.service import IndicatorService
from screener.modules.market.infrastructure.models import (
    DailyBarRecord,
    Stock,
    WatchlistPipelineExecution,
)
from screener.modules.market.pipeline import DailyWatchlistPipeline, ExecutionStatus, TriggerType
from screener.modules.market.ranking import RankedCandidate
from screener.modules.market.screening import ScreeningResult
from screener.modules.market.watchlist import WatchlistRepository
from screener.shared.database import Base

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def candidate(symbol: str) -> RankedCandidate:
    result = ScreeningResult(symbol=symbol, passed=True)
    return RankedCandidate(
        symbol=symbol,
        rank=1,
        total_score=Decimal("90"),
        component_scores={"trend": Decimal("90")},
        source_result=result,
    )


def pipeline(
    sessions: async_sessionmaker[AsyncSession],
    *,
    ranked: list[RankedCandidate] | None = None,
) -> tuple[DailyWatchlistPipeline, AsyncMock, Mock, Mock]:
    sync = AsyncMock()
    scanner = Mock()
    scanner.scan.return_value = [ScreeningResult(symbol="NEW", passed=True)]
    ranker = Mock()
    ranker.rank.return_value = [candidate("NEW")] if ranked is None else ranked
    value = DailyWatchlistPipeline(sessions, sync, IndicatorService(), scanner, ranker)
    value._inputs = AsyncMock(return_value=[])  # type: ignore[method-assign]
    return value, sync, scanner, ranker


async def seed_success(
    sessions: async_sessionmaker[AsyncSession], day: date, symbol: str = "OLD"
) -> WatchlistPipelineExecution:
    async with sessions() as session:
        execution = WatchlistPipelineExecution(
            trading_date=day,
            trigger_type="manual",
            status="succeeded",
            stage="completed",
            started_at=datetime.now(UTC) - timedelta(hours=1),
        )
        session.add(execution)
        await WatchlistRepository(session).save(day, [candidate(symbol)])
        await session.commit()
        return execution


async def symbols(sessions: async_sessionmaker[AsyncSession], day: date) -> list[str]:
    async with sessions() as session:
        return [entry.symbol for entry in await WatchlistRepository(session).list(day)]


async def test_normal_calls_sync_and_reanalysis_never_does(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    normal_day = date(2026, 7, 30)
    normal, normal_sync, _, _ = pipeline(sessions, ranked=[])
    assert (await normal.run(normal_day)).status == ExecutionStatus.SUCCEEDED
    normal_sync.all.assert_awaited_once()

    forced_day = date(2026, 7, 31)
    await seed_success(sessions, forced_day)
    forced, forced_sync, _, _ = pipeline(sessions)
    result = await forced.run(forced_day, TriggerType.MANUAL_REANALYSIS, force_reanalysis=True)
    assert result.status == ExecutionStatus.SUCCEEDED
    forced_sync.all.assert_not_awaited()


async def test_normal_after_stale_reanalysis_recovers_without_sync(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    day = date(2026, 7, 31)
    await seed_success(sessions, day)
    async with sessions() as session:
        stale = WatchlistPipelineExecution(
            trading_date=day,
            trigger_type="manual_reanalysis",
            status="running",
            stage="candidate_scanning",
            started_at=datetime.now(UTC) - timedelta(hours=3),
        )
        session.add(stale)
        await session.commit()
        stale_id = stale.id
    value, sync, _, _ = pipeline(sessions)
    value.stale_after_seconds = 1
    result = await value.run(day)
    assert result.skipped_reason == "already_completed"
    sync.all.assert_not_awaited()
    async with sessions() as session:
        recovered = await session.get(WatchlistPipelineExecution, stale_id)
    assert recovered is not None and recovered.status == "failed"


async def test_reanalysis_uses_only_stored_bars_through_selected_date(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    target = date(2026, 7, 31)
    async with sessions() as session:
        session.add(
            Stock(
                symbol="005930",
                name="Samsung",
                market="KOSPI",
                currency="KRW",
                country="KR",
                security_type="common_stock",
                listing_status="listed",
                is_active=True,
            )
        )
        for offset in range(62):
            bar_day = target - timedelta(days=61 - offset)
            session.add(
                DailyBarRecord(
                    symbol="005930",
                    trading_date=bar_day,
                    open=1000,
                    high=1100,
                    low=900,
                    close=1000,
                    volume=100,
                    source="stored",
                    provider_timestamp=datetime.now(UTC),
                )
            )
        session.add(
            DailyBarRecord(
                symbol="005930",
                trading_date=target + timedelta(days=1),
                open=2000,
                high=2100,
                low=1900,
                close=2000,
                volume=200,
                source="future",
                provider_timestamp=datetime.now(UTC),
            )
        )
        await session.commit()
    value, _, _, _ = pipeline(sessions)
    del value._inputs
    inputs = await value._inputs(target)
    assert len(inputs) == 1
    assert inputs[0].bars[-1].trading_date == target
    assert all(bar.trading_date <= target for bar in inputs[0].bars)


async def test_successful_reanalysis_is_distinct_and_atomically_replaces_entries(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    day = date(2026, 7, 31)
    previous = await seed_success(sessions, day)
    value, _, _, _ = pipeline(sessions)
    result = await value.run(day, TriggerType.MANUAL_REANALYSIS, force_reanalysis=True)
    assert result.execution_id != previous.id
    assert result.trigger_type == TriggerType.MANUAL_REANALYSIS
    assert await symbols(sessions, day) == ["NEW"]


async def test_successful_empty_reanalysis_intentionally_clears_entries(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    day = date(2026, 7, 31)
    await seed_success(sessions, day)
    value, _, _, _ = pipeline(sessions, ranked=[])
    result = await value.run(day, TriggerType.MANUAL_REANALYSIS, force_reanalysis=True)
    assert result.status == ExecutionStatus.SUCCEEDED
    assert await symbols(sessions, day) == []


@pytest.mark.parametrize("failure", ["scanner", "ranker"])
async def test_calculation_failure_preserves_previous_entries(
    sessions: async_sessionmaker[AsyncSession], failure: str
) -> None:
    day = date(2026, 7, 31)
    await seed_success(sessions, day)
    value, _, scanner, ranker = pipeline(sessions)
    getattr(
        scanner if failure == "scanner" else ranker, "scan" if failure == "scanner" else "rank"
    ).side_effect = RuntimeError("calculation failed")
    result = await value.run(day, TriggerType.MANUAL_REANALYSIS, force_reanalysis=True)
    assert result.status == ExecutionStatus.FAILED
    assert await symbols(sessions, day) == ["OLD"]


async def test_persistence_failure_preserves_previous_entries(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    day = date(2026, 7, 31)
    await seed_success(sessions, day)

    async def fail_save(self: WatchlistRepository, trading_date: date, values: object) -> None:
        await self.delete(trading_date)
        raise RuntimeError("persistence failed")

    monkeypatch.setattr(WatchlistRepository, "save", fail_save)
    value, _, _, _ = pipeline(sessions)
    result = await value.run(day, TriggerType.MANUAL_REANALYSIS, force_reanalysis=True)
    assert result.status == ExecutionStatus.FAILED
    assert await symbols(sessions, day) == ["OLD"]
    async with sessions() as session:
        successful = list(
            (
                await session.scalars(
                    select(WatchlistPipelineExecution).where(
                        WatchlistPipelineExecution.trading_date == day,
                        WatchlistPipelineExecution.status == "succeeded",
                    )
                )
            ).all()
        )
    assert len(successful) == 1


async def test_final_commit_failure_preserves_previous_entries(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    day = date(2026, 7, 31)
    await seed_success(sessions, day)
    original_commit = AsyncSession.commit

    async def fail_replacement_commit(session: AsyncSession) -> None:
        if any(
            isinstance(value, WatchlistPipelineExecution)
            and value.trigger_type == "manual_reanalysis"
            and value.status == "succeeded"
            for value in session.identity_map.values()
        ):
            raise RuntimeError("final commit failed")
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", fail_replacement_commit)
    value, _, _, _ = pipeline(sessions)
    result = await value.run(day, TriggerType.MANUAL_REANALYSIS, force_reanalysis=True)
    assert result.status == ExecutionStatus.FAILED
    assert await symbols(sessions, day) == ["OLD"]
