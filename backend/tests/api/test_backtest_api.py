"""Contract tests for the backtest lifecycle REST API."""

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from screener.api.backtests.dependencies import get_backtest_service
from screener.main import app
from screener.modules.backtest import BacktestExecutionError, BacktestRun, BacktestStatus


class FakeService:
    def __init__(self) -> None:
        self.runs: list[BacktestRun] = []

    async def create(
        self,
        strategy_name: str,
        strategy_version: str | None,
        start_date: date,
        end_date: date,
        parameters: dict[str, object],
        data_as_of: datetime | None,
    ) -> BacktestRun:
        run = BacktestRun(
            strategy_name=strategy_name.strip(),
            strategy_version=strategy_version,
            start_date=start_date,
            end_date=end_date,
            parameters=parameters,
            data_as_of=data_as_of,
            status=BacktestStatus.COMPLETED,
            created_at=datetime(2026, 7, 28, tzinfo=UTC),
        )
        self.runs.append(run)
        return run

    async def list(self, limit: int, offset: int) -> list[BacktestRun]:
        return self.runs[offset : offset + limit]

    async def get(self, run_id: UUID) -> BacktestRun:
        from screener.modules.backtest import BacktestNotFoundError

        run = next((run for run in self.runs if run.id == run_id), None)
        if run is None:
            raise BacktestNotFoundError
        return run


@pytest.fixture
def client() -> TestClient:
    service = FakeService()
    app.dependency_overrides[get_backtest_service] = lambda: service
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()


def test_create_backtest_returns_completed_metadata(client: TestClient) -> None:
    response = client.post(
        "/api/v1/backtests",
        json={
            "strategy_name": "breakout",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "strategy_version": "1.0",
            "data_as_of": "2026-07-28T00:00:00Z",
            "parameters": {"risk": {"stop_loss_pct": 5}},
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == BacktestStatus.COMPLETED
    assert response.json()["parameters"] == {"risk": {"stop_loss_pct": 5}}
    assert response.json()["strategy_version"] == "1.0"
    assert response.json()["failure_code"] is None
    assert response.json()["started_at"] is None


def test_list_and_get_backtests(client: TestClient) -> None:
    created = client.post(
        "/api/v1/backtests",
        json={"strategy_name": "breakout", "start_date": "2025-01-01", "end_date": "2025-12-31"},
    ).json()
    assert client.get("/api/v1/backtests").json() == [created]
    assert client.get(f"/api/v1/backtests/{created['id']}").json() == created


def test_invalid_request_and_missing_run(client: TestClient) -> None:
    invalid = client.post(
        "/api/v1/backtests",
        json={"strategy_name": "breakout", "start_date": "2025-12-31", "end_date": "2025-01-01"},
    )
    assert invalid.status_code == 422
    assert client.get("/api/v1/backtests/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/v1/backtests/not-a-uuid").status_code == 422


def test_request_validation(client: TestClient) -> None:
    base = {"strategy_name": "breakout", "start_date": "2025-01-01", "end_date": "2025-01-02"}
    assert (
        client.post("/api/v1/backtests", json={**base, "strategy_name": "   "}).status_code == 422
    )
    assert (
        client.post(
            "/api/v1/backtests", json={**base, "data_as_of": "2026-01-01T00:00:00"}
        ).status_code
        == 422
    )
    assert client.post("/api/v1/backtests", json={**base, "unexpected": True}).status_code == 422


def test_executor_failure_response_is_sanitized(client: TestClient) -> None:
    class FailingService(FakeService):
        async def create(self, *args: object, **kwargs: object) -> BacktestRun:
            try:
                raise RuntimeError("database password = abc123")
            except RuntimeError as exc:
                raise BacktestExecutionError("Backtest execution failed") from exc

    app.dependency_overrides[get_backtest_service] = FailingService
    response = client.post(
        "/api/v1/backtests",
        json={"strategy_name": "breakout", "start_date": "2025-01-01", "end_date": "2025-01-02"},
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Backtest execution failed"}
    assert "abc123" not in response.text


def test_openapi_documents_foundation_only(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/backtests" in paths
    assert "/api/v1/backtests/{run_id}" in paths
    schema = client.get("/openapi.json").json()["components"]["schemas"]
    assert {"strategy_version", "data_as_of"} <= set(schema["CreateBacktestRequest"]["properties"])
    assert {"failure_code", "failure_message"} <= set(schema["BacktestResponse"]["properties"])
    response_fields = set(schema["BacktestResponse"]["properties"])
    assert {
        "id",
        "strategy_name",
        "strategy_version",
        "parameters",
        "data_as_of",
        "status",
        "failure_code",
        "failure_message",
        "started_at",
        "completed_at",
    } <= response_fields
    assert not {"trades", "returns", "analytics", "equity_curve"} & response_fields
