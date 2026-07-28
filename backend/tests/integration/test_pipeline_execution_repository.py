"""PostgreSQL-only ownership and crash-recovery integration tests."""

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from screener.modules.market.infrastructure.models import WatchlistPipelineExecution
from screener.modules.market.pipeline import (
    ExecutionAcquireStatus,
    ExecutionStatus,
    PipelineExecutionRepository,
    PipelineStage,
    TriggerType,
)
from screener.modules.market.pipeline.repository import WATCHLIST_PIPELINE_LOCK_NAMESPACE

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="a PostgreSQL test database URL is required"
)


@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    assert TEST_DATABASE_URL is not None
    url = TEST_DATABASE_URL
    if not url.startswith("postgresql+asyncpg://"):
        pytest.fail("PostgreSQL integration tests require postgresql+asyncpg")
    if not url.partition("?")[0].endswith("_test"):
        pytest.fail("PostgreSQL integration tests require a database whose name ends in _test")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(delete(WatchlistPipelineExecution))
        await session.commit()
    yield factory
    async with factory() as session:
        await session.execute(delete(WatchlistPipelineExecution))
        await session.commit()
    await engine.dispose()


async def acquire(sessions: async_sessionmaker[AsyncSession], day: date, stale: int = 7200):
    async with sessions() as session:
        return await PipelineExecutionRepository(session).acquire(day, TriggerType.MANUAL, stale)


async def test_acquire_running_success_failed_and_retry(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    day = date(2026, 7, 27)
    first = await acquire(sessions, day)
    assert first.status == ExecutionAcquireStatus.ACQUIRED
    assert (await acquire(sessions, day)).status == ExecutionAcquireStatus.ALREADY_RUNNING
    async with sessions() as session:
        await PipelineExecutionRepository(session).finish(
            first.execution.id, status=ExecutionStatus.FAILED, stage=PipelineStage.MARKET_SYNC
        )
    retry = await acquire(sessions, day)
    assert retry.status == ExecutionAcquireStatus.ACQUIRED
    async with sessions() as session:
        await PipelineExecutionRepository(session).finish(
            retry.execution.id, status=ExecutionStatus.SUCCEEDED, stage=PipelineStage.COMPLETED
        )
    assert (await acquire(sessions, day)).status == ExecutionAcquireStatus.ALREADY_COMPLETED


async def test_stale_recovery_is_atomic_and_preserves_history(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    day = date(2026, 7, 28)
    stale = WatchlistPipelineExecution(
        trading_date=day,
        trigger_type="scheduled",
        status="running",
        stage="candidate_scanning",
        started_at=datetime.now(UTC) - timedelta(seconds=10),
    )
    async with sessions() as session:
        session.add(stale)
        await session.commit()
        stale_id = stale.id
    one, two = await asyncio.gather(acquire(sessions, day, 1), acquire(sessions, day, 1))
    assert {one.status, two.status} == {
        ExecutionAcquireStatus.ACQUIRED,
        ExecutionAcquireStatus.ALREADY_RUNNING,
    }
    winner = one if one.status == ExecutionAcquireStatus.ACQUIRED else two
    assert winner.recovered_execution_id == stale_id
    async with sessions() as session:
        history = list((await session.scalars(select(WatchlistPipelineExecution))).all())
    assert len(history) == 2
    recovered = next(item for item in history if item.id == stale_id)
    assert recovered.status == "failed"
    assert recovered.stage == "candidate_scanning"
    assert recovered.finished_at is not None
    assert recovered.error_code == "stale_execution_recovered"
    assert recovered.error_detail == "Execution exceeded stale timeout"
    assert sum(item.status == "running" for item in history) == 1


async def test_acquire_waits_for_namespaced_date_lock(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    day = date(2026, 7, 29)
    async with sessions() as lock_session:
        await lock_session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :trading_date)"),
            {
                "namespace": WATCHLIST_PIPELINE_LOCK_NAMESPACE,
                "trading_date": day.toordinal(),
            },
        )
        competing_acquire = asyncio.create_task(acquire(sessions, day))
        await asyncio.sleep(0.1)
        assert not competing_acquire.done()
        await lock_session.rollback()

    result = await asyncio.wait_for(competing_acquire, timeout=2)
    assert result.status == ExecutionAcquireStatus.ACQUIRED
