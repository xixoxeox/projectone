"""Focused administrator API contract tests for watchlist reanalysis."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from screener.api.admin_watchlist_pipeline import get_pipeline, router
from screener.modules.identity.presentation.dependencies import get_current_user
from screener.modules.market.pipeline import ExecutionStatus, PipelineResult, PipelineStage


def result(*, skipped_reason: str | None = None) -> PipelineResult:
    return PipelineResult(
        trading_date=date(2026, 7, 31),
        status=ExecutionStatus.SKIPPED if skipped_reason else ExecutionStatus.SUCCEEDED,
        started_at=datetime.now(UTC),
        stage=PipelineStage.DUPLICATE_CHECK if skipped_reason else PipelineStage.COMPLETED,
        skipped_reason=skipped_reason,
    )


def client(pipeline: AsyncMock, *, admin: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_pipeline] = lambda: pipeline
    if admin:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
    return TestClient(app)


def test_admin_reanalysis_request_is_accepted() -> None:
    pipeline = AsyncMock()
    pipeline.run.return_value = result()
    with client(pipeline) as value:
        response = value.post(
            "/api/v1/admin/watchlist/run",
            json={"trading_date": "2026-07-31", "force_reanalysis": True},
        )
    assert response.status_code == 200
    pipeline.run.assert_awaited_once()
    assert pipeline.run.await_args.kwargs == {"force_reanalysis": True}
    assert str(pipeline.run.await_args.args[0]) == "2026-07-31"
    assert pipeline.run.await_args.args[1] == "manual_reanalysis"


def test_force_reanalysis_requires_trading_date() -> None:
    pipeline = AsyncMock()
    with client(pipeline) as value:
        response = value.post("/api/v1/admin/watchlist/run", json={"force_reanalysis": True})
    assert response.status_code == 422
    pipeline.run.assert_not_awaited()


def test_force_reanalysis_conflicts_are_http_409() -> None:
    for reason in ("prior_success_required", "already_running"):
        pipeline = AsyncMock()
        pipeline.run.return_value = result(skipped_reason=reason)
        with client(pipeline) as value:
            response = value.post(
                "/api/v1/admin/watchlist/run",
                json={"trading_date": "2026-07-31", "force_reanalysis": True},
            )
        assert response.status_code == 409


def test_watchlist_run_requires_admin_authentication() -> None:
    with client(AsyncMock(), admin=False) as value:
        response = value.post(
            "/api/v1/admin/watchlist/run",
            json={"trading_date": "2026-07-31", "force_reanalysis": True},
        )
    assert response.status_code == 401
