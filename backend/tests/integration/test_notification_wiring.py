"""Production-boundary wiring tests for daily watchlist notifications."""

from datetime import date
from functools import partial
from inspect import signature
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screener.api.admin_watchlist_pipeline import (
    router as watchlist_pipeline_router,
)
from screener.api.admin_watchlist_pipeline import (
    watchlist_pipeline,
)
from screener.main import app
from screener.modules.identity.presentation.dependencies import get_current_user
from screener.modules.market.pipeline import (
    DailyWatchlistPipeline,
    ExecutionStatus,
    PipelineResult,
    TriggerType,
)
from screener.modules.market.presentation.admin_router import (
    coordinator,
    router,
)
from screener.modules.market.scheduler import build_scheduler
from screener.modules.market.sync import SyncResult
from screener.modules.notifications import NotificationPublishingPipeline, NotificationService


class RecordingProvider:
    name = "recording"

    def __init__(self) -> None:
        self.events: list[object] = []

    async def send(self, event: object) -> None:
        self.events.append(event)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_startup_constructs_singleton_boundary_used_by_scheduler() -> None:
    with TestClient(app):
        boundary = app.state.notification_publishing_pipeline
        assert isinstance(boundary, NotificationPublishingPipeline)
        jobs = app.state.scheduler.get_jobs()
        assert {job.id for job in jobs} == {"stock_master", "daily_bars", "daily_watchlist"}
        scheduled = next(job.func for job in jobs if job.id == "daily_watchlist")
        assert isinstance(scheduled, partial)
        assert scheduled.func.__self__ is boundary
        assert scheduled.args == (TriggerType.SCHEDULED,)


@pytest.mark.anyio
async def test_scheduled_watchlist_does_not_duplicate_synchronization() -> None:
    stocks = SimpleNamespace(run=AsyncMock())
    bars = SimpleNamespace(run=AsyncMock())
    provider = RecordingProvider()

    async def daily_pipeline(trigger: TriggerType) -> PipelineResult:
        return PipelineResult(date(2026, 7, 28), UUID(int=1), trigger, ExecutionStatus.SUCCEEDED)

    boundary = NotificationPublishingPipeline(daily_pipeline, NotificationService(provider))
    scheduler = build_scheduler(stocks, bars, boundary)

    scheduled = next(job.func for job in scheduler.get_jobs() if job.id == "daily_watchlist")
    await scheduled()

    stocks.run.assert_not_awaited()
    bars.run.assert_not_awaited()
    assert len(provider.events) == 1
    assert provider.events[0].trigger_type is TriggerType.SCHEDULED


def test_daily_pipeline_has_no_synchronization_dependency() -> None:
    parameters = signature(DailyWatchlistPipeline).parameters
    assert set(parameters) == {"sessions", "indicators", "scanner", "ranker", "stale_after"}


def test_manual_endpoint_uses_boundary_and_reaches_notification_service() -> None:
    provider = RecordingProvider()

    async def daily_pipeline(trigger: TriggerType) -> PipelineResult:
        return PipelineResult(
            date(2026, 7, 28),
            UUID(int=1),
            trigger,
            ExecutionStatus.SUCCEEDED,
        )

    boundary = NotificationPublishingPipeline(daily_pipeline, NotificationService(provider))
    test_app = FastAPI()
    test_app.include_router(watchlist_pipeline_router, prefix="/api/v1")
    test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
    test_app.dependency_overrides[watchlist_pipeline] = lambda: boundary

    with TestClient(test_app) as client:
        response = client.post("/api/v1/admin/watchlist-pipeline/run")

    assert response.status_code == 200
    assert response.json()["trigger_type"] == TriggerType.MANUAL
    assert len(provider.events) == 1
    assert provider.events[0].trigger_type is TriggerType.MANUAL


def test_raw_sync_endpoints_remain_direct_and_do_not_publish_notifications() -> None:
    stocks = SimpleNamespace(
        run=AsyncMock(
            return_value=SyncResult(
                job_name="stock_master",
                status="succeeded",
                duration_ms=1,
                inserted_rows=0,
                updated_rows=0,
                skipped_rows=0,
            )
        )
    )
    bars = SimpleNamespace(
        run=AsyncMock(
            return_value=SyncResult(
                job_name="daily_bars",
                status="succeeded",
                duration_ms=1,
                inserted_rows=0,
                updated_rows=0,
                skipped_rows=0,
            )
        )
    )

    async def all_jobs() -> list[SyncResult]:
        return [await stocks.run(), await bars.run()]

    sync = SimpleNamespace(stocks=stocks, bars=bars, all=AsyncMock(side_effect=all_jobs))
    boundary = SimpleNamespace(run=AsyncMock())
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
    test_app.dependency_overrides[coordinator] = lambda: sync
    test_app.dependency_overrides[watchlist_pipeline] = lambda: boundary

    with TestClient(test_app) as client:
        assert client.post("/api/v1/admin/sync/stocks").status_code == 200
        assert client.post("/api/v1/admin/sync/daily-bars").status_code == 200
        assert client.post("/api/v1/admin/sync/all").status_code == 200

    assert stocks.run.await_count == 2
    assert bars.run.await_count == 2
    sync.all.assert_awaited_once()
    boundary.run.assert_not_awaited()
