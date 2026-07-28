"""Production-boundary wiring tests for daily watchlist notifications."""

from datetime import date
from functools import partial
from types import SimpleNamespace
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from screener.main import app
from screener.modules.identity.presentation.dependencies import get_current_user
from screener.modules.market.pipeline import ExecutionStatus, PipelineResult, TriggerType
from screener.modules.market.presentation.admin_router import router, watchlist_pipeline
from screener.modules.notifications import NotificationPublishingPipeline, NotificationService


class RecordingProvider:
    name = "recording"

    def __init__(self) -> None:
        self.events: list[object] = []

    async def send(self, event: object) -> None:
        self.events.append(event)


def test_startup_constructs_singleton_boundary_used_by_scheduler() -> None:
    with TestClient(app):
        boundary = app.state.notification_publishing_pipeline
        assert isinstance(boundary, NotificationPublishingPipeline)
        jobs = app.state.scheduler.get_jobs()
        assert len(jobs) == 1
        scheduled = jobs[0].func
        assert isinstance(scheduled, partial)
        assert scheduled.func.__self__ is boundary
        assert scheduled.args == (TriggerType.SCHEDULED,)


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
    test_app.include_router(router, prefix="/api/v1")
    test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
    test_app.dependency_overrides[watchlist_pipeline] = lambda: boundary

    with TestClient(test_app) as client:
        response = client.post("/api/v1/admin/sync/watchlist/run")

    assert response.status_code == 200
    assert response.json()["trigger_type"] == TriggerType.MANUAL
    assert len(provider.events) == 1
    assert provider.events[0].trigger_type is TriggerType.MANUAL
