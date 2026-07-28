"""Contract tests for the backtest lifecycle REST API."""

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from screener.api.backtests.dependencies import get_backtest_service
from screener.main import app
from screener.modules.backtest import BacktestRun, BacktestStatus


class FakeService:
    def __init__(self) -> None:
        self.runs: list[BacktestRun] = []

    async def create(
        self, strategy_name: str, start_date: date, end_date: date, parameters: dict[str, object]
    ) -> BacktestRun:
        run = BacktestRun(
            strategy_name=strategy_name.strip(),
            start_date=start_date,
            end_date=end_date,
            parameters=parameters,
            created_at=datetime(2026, 7, 28, tzinfo=UTC),
        )
        self.runs.append(run)
        return run

    async def list(self, limit: int, offset: int) -> list[BacktestRun]:
        return self.runs[offset : offset + limit]

    async def get(self, run_id: UUID) -> BacktestRun | None:
        return next((run for run in self.runs if run.id == run_id), None)


@pytest.fixture
def client() -> TestClient:
    service = FakeService()
    app.dependency_overrides[get_backtest_service] = lambda: service
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()


def test_create_backtest_returns_pending_metadata(client: TestClient) -> None:
    response = client.post(
        "/api/v1/backtests",
        json={
            "strategy_name": "breakout",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "parameters": {"window": 20},
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == BacktestStatus.PENDING
    assert response.json()["parameters"] == {"window": 20}
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


def test_openapi_documents_foundation_only(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/backtests" in paths
    assert "/api/v1/backtests/{run_id}" in paths
