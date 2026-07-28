"""Contract tests for the backtest REST API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from screener.api.backtests.dependencies import get_backtest_service
from screener.main import app
from screener.modules.backtest import BacktestExitReason, BacktestRun, BacktestTrade
from screener.modules.backtest.service import BacktestNotFoundError, BacktestRangeError


class FakeService:
    def __init__(self) -> None:
        self.runs: dict[UUID, BacktestRun] = {}
        self.trades: dict[UUID, list[BacktestTrade]] = {}

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
            .complete({"entered_trades": 1, "net_profit": "12.34000000"})
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

    async def list_trades(
        self,
        run_id: UUID,
        limit: int,
        offset: int,
        symbol: str | None,
        exit_reason: BacktestExitReason | None,
    ) -> list[BacktestTrade]:
        await self.get(run_id)
        trades = self.trades.get(run_id, [])
        if symbol is not None:
            trades = [trade for trade in trades if trade.symbol == symbol]
        if exit_reason is not None:
            trades = [trade for trade in trades if trade.exit_reason == exit_reason]
        return trades[offset : offset + limit]


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


def trade(run_id: UUID, symbol: str, reason: BacktestExitReason, day: int) -> BacktestTrade:
    return BacktestTrade(
        uuid4(),
        run_id,
        symbol,
        date(2026, 1, day),
        date(2026, 1, day + 1),
        Decimal("12345.67890123"),
        10,
        date(2026, 1, day + 2),
        Decimal("12500.00000000"),
        reason,
        Decimal("1543.21098770"),
        Decimal("37.26851835"),
        Decimal("187.50000000"),
        Decimal("248.45678902"),
        Decimal("1318.44246935"),
        1,
    )


def test_create_get_list_and_parameter_persistence(client: TestClient) -> None:
    created = client.post("/api/v1/backtests", json=payload())
    assert created.status_code == 201
    body = created.json()
    assert body["strategy_name"] == "watchlist_entry"
    assert body["strategy_version"] == "1"
    assert body["parameters"] == {}
    assert body["data_as_of"] == "2026-01-21T09:00:00+09:00"
    assert body["result"] == {"entered_trades": 1, "net_profit": "12.34000000"}

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


def test_trades_are_returned_with_pagination_and_filters(
    client: TestClient, service: FakeService
) -> None:
    run_id = UUID(client.post("/api/v1/backtests", json=payload()).json()["id"])
    service.trades[run_id] = [
        trade(run_id, "005930", BacktestExitReason.TAKE_PROFIT, 1),
        trade(run_id, "000660", BacktestExitReason.STOP_LOSS, 4),
        trade(run_id, "005930", BacktestExitReason.STOP_LOSS, 7),
    ]
    response = client.get(f"/api/v1/backtests/{run_id}/trades")
    assert response.status_code == 200
    assert [row["symbol"] for row in response.json()] == ["005930", "000660", "005930"]
    assert response.json()[0]["entry_price"] == "12345.67890123"
    assert [
        row["symbol"]
        for row in client.get(f"/api/v1/backtests/{run_id}/trades?limit=1&offset=1").json()
    ] == ["000660"]
    by_symbol = client.get(f"/api/v1/backtests/{run_id}/trades?symbol=005930").json()
    assert len(by_symbol) == 2 and {row["symbol"] for row in by_symbol} == {"005930"}
    by_reason = client.get(f"/api/v1/backtests/{run_id}/trades?exit_reason=take_profit").json()
    assert len(by_reason) == 1 and by_reason[0]["exit_reason"] == "take_profit"


def test_trades_for_unknown_run_return_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/backtests/{uuid4()}/trades")
    assert response.status_code == 404
    assert response.json() == {"detail": "Backtest run not found"}


@pytest.mark.parametrize("query", ["limit=0", "limit=501", "offset=-1", "exit_reason=bad"])
def test_invalid_trade_parameters_return_422(client: TestClient, query: str) -> None:
    assert client.get(f"/api/v1/backtests/{uuid4()}/trades?{query}").status_code == 422


def test_openapi_contains_all_backtest_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"get", "post"} <= set(paths["/api/v1/backtests"])
    assert "get" in paths["/api/v1/backtests/{run_id}"]
    assert "get" in paths["/api/v1/backtests/{run_id}/trades"]


@pytest.mark.parametrize("version", [None, "1"])
def test_supported_strategy_versions_succeed(client: TestClient, version: str | None) -> None:
    response = client.post("/api/v1/backtests", json=payload() | {"strategy_version": version})
    assert response.status_code == 201
