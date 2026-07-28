"""Contract tests for the backtest REST API."""

from datetime import date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from screener.api.backtests.dependencies import get_backtest_service
from screener.main import app
from screener.modules.backtest import BacktestRun
from screener.modules.backtest.service import BacktestNotFoundError, BacktestRangeError


class FakeService:
    def __init__(self) -> None:
        self.runs: dict[UUID, BacktestRun] = {}

    async def create(
        self,
        strategy_name: str,
        start_date: date,
        end_date: date,
        strategy_version: str | None = None,
        parameters: dict[str, object] | None = None,
        data_as_of: datetime | None = None,
    ) -> BacktestRun:
        if (end_date - start_date).days > 30:
            raise BacktestRangeError("date range cannot exceed 30 days")
        run = (
            BacktestRun.create(
                strategy_name, start_date, end_date, strategy_version, parameters, data_as_of
            )
            .start()
            .complete({})
        )
        self.runs[run.id] = run
        return run

    async def get(self, run_id: UUID) -> BacktestRun:
        try:
            return self.runs[run_id]
        except KeyError as exc:
            raise BacktestNotFoundError(str(run_id)) from exc

    async def list(self) -> list[BacktestRun]:
        return list(self.runs.values())


@pytest.fixture
def service() -> FakeService:
    value = FakeService()
    app.dependency_overrides[get_backtest_service] = lambda: value
    return value


@pytest.fixture
def client(service: FakeService) -> TestClient:
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()


def payload() -> dict[str, object]:
    return {
        "strategy_name": "watchlist_entry",
        "strategy_version": "1",
        "parameters": {},
        "start_date": "2026-01-01",
        "end_date": "2026-01-20",
        "data_as_of": "2026-01-21T09:00:00+09:00",
    }


def test_create_get_list_and_parameter_persistence(client: TestClient) -> None:
    created = client.post("/api/v1/backtests", json=payload())
    assert created.status_code == 201
    body = created.json()
    assert body["strategy_name"] == "watchlist_entry"
    assert body["strategy_version"] == "1"
    assert body["parameters"] == {}
    assert body["data_as_of"] == "2026-01-21T09:00:00+09:00"

    assert client.get(f"/api/v1/backtests/{body['id']}").json() == body
    assert client.get("/api/v1/backtests").json() == [body]


@pytest.mark.parametrize(
    ("changes", "detail"),
    [
        ({"start_date": "2026-02-01", "end_date": "2026-01-01"}, "start_date"),
        ({"end_date": "2026-03-01"}, "cannot exceed"),
        ({"strategy_name": "other"}, "strategy_name"),
        ({"strategy_version": "2"}, "strategy_version"),
        ({"data_as_of": "2026-01-21T09:00:00"}, "timezone-aware"),
    ],
)
def test_invalid_create_requests(
    client: TestClient, changes: dict[str, object], detail: str
) -> None:
    request = payload() | changes
    response = client.post("/api/v1/backtests", json=request)
    assert response.status_code == 422
    assert detail in response.text


def test_missing_run_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/backtests/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Backtest run not found"}


def test_openapi_contains_all_backtest_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"get", "post"} <= set(paths["/api/v1/backtests"])
    assert "get" in paths["/api/v1/backtests/{run_id}"]
    assert "get" in paths["/api/v1/backtests/{run_id}/trades"]


@pytest.mark.parametrize("version", [None, "1"])
def test_supported_strategy_versions_succeed(client: TestClient, version: str | None) -> None:
    response = client.post("/api/v1/backtests", json=payload() | {"strategy_version": version})
    assert response.status_code == 201
