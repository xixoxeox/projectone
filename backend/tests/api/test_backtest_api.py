"""Contract tests for the backtest REST API."""

from __future__ import annotations

from datetime import UTC, date, datetime
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
        self.trades: list[BacktestTrade] = []

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
            .complete({"entered_trades": 2, "net_profit": "123.45000000"})
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
        matches = [trade for trade in self.trades if trade.run_id == run_id]
        if symbol is not None:
            matches = [trade for trade in matches if trade.symbol == symbol]
        if exit_reason is not None:
            matches = [trade for trade in matches if trade.exit_reason is exit_reason]
        return matches[offset : offset + limit]


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
        "strategy_name": " watchlist_entry ",
        "strategy_version": " 1 ",
        "parameters": {"position_size": 500000},
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
    assert body["parameters"] == {"position_size": 500000}
    assert body["result"] == {"entered_trades": 2, "net_profit": "123.45000000"}
    assert body["data_as_of"] == "2026-01-21T09:00:00+09:00"

    assert client.get(f"/api/v1/backtests/{body['id']}").json() == body
    assert client.get("/api/v1/backtests").json() == [body]


@pytest.mark.parametrize(
    ("changes", "detail"),
    [
        ({"start_date": "2026-02-01", "end_date": "2026-01-01"}, "start_date"),
        ({"end_date": "2026-03-01"}, "cannot exceed"),
        ({"strategy_name": "   "}, "strategy_name"),
        ({"strategy_name": "breakout"}, "watchlist_entry"),
        ({"strategy_version": "2"}, "strategy_version"),
        ({"parameters": {"initial_capital": True}}, "initial_capital"),
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


def _trade(run_id: UUID, symbol: str, reason: BacktestExitReason) -> BacktestTrade:
    return BacktestTrade(
        id=uuid4(),
        run_id=run_id,
        symbol=symbol,
        signal_date=date(2026, 1, 2),
        entry_date=date(2026, 1, 3),
        entry_price=Decimal("100.12345678"),
        quantity=10,
        exit_date=date(2026, 1, 4),
        exit_price=Decimal("110.12345678"),
        exit_reason=reason,
        gross_pnl=Decimal("100.00000000"),
        commission=Decimal("0.31537037"),
        tax=Decimal("1.65185185"),
        slippage_cost=Decimal("2.10000000"),
        net_pnl=Decimal("98.03277778"),
        holding_days=1,
        created_at=datetime(2026, 1, 5, tzinfo=UTC),
    )


def test_trades_pagination_and_filters(client: TestClient, service: FakeService) -> None:
    run_id = UUID(client.post("/api/v1/backtests", json=payload()).json()["id"])
    service.trades = [
        _trade(run_id, "005930", BacktestExitReason.TAKE_PROFIT),
        _trade(run_id, "000660", BacktestExitReason.STOP_LOSS),
        _trade(run_id, "035420", BacktestExitReason.TAKE_PROFIT),
    ]

    page = client.get(f"/api/v1/backtests/{run_id}/trades?limit=1&offset=1")
    assert page.status_code == 200
    assert [item["symbol"] for item in page.json()] == ["000660"]
    symbol = client.get(f"/api/v1/backtests/{run_id}/trades?symbol=035420")
    assert [item["symbol"] for item in symbol.json()] == ["035420"]
    reason = client.get(f"/api/v1/backtests/{run_id}/trades?exit_reason=take_profit")
    assert [item["symbol"] for item in reason.json()] == ["005930", "035420"]


def test_trades_for_missing_run_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/backtests/{uuid4()}/trades")
    assert response.status_code == 404


def test_openapi_contains_all_backtest_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"get", "post"} <= set(paths["/api/v1/backtests"])
    assert "get" in paths["/api/v1/backtests/{run_id}"]
    assert "get" in paths["/api/v1/backtests/{run_id}/trades"]
