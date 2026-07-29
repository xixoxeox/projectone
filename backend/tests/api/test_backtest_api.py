"""Contract tests for the backtest REST API."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from screener.api.backtests.dependencies import get_backtest_service
from screener.main import app
from screener.modules.backtest import (
    BacktestExitReason,
    BacktestRun,
    BacktestTrade,
    PortfolioSnapshot,
)
from screener.modules.backtest.analysis import analyze_backtest_trades
from screener.modules.backtest.service import (
    BacktestAnalysisUnavailableError,
    BacktestNotFoundError,
    BacktestRangeError,
)


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
            .complete({"entered_trades": 2, "net_profit": "1250.00000000"})
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
        if run_id not in self.runs:
            raise BacktestNotFoundError(str(run_id))
        trades = self.trades.get(run_id, [])
        if symbol is not None:
            trades = [trade for trade in trades if trade.symbol == symbol]
        if exit_reason is not None:
            trades = [trade for trade in trades if trade.exit_reason == exit_reason]
        return trades[offset : offset + limit]

    async def analyze(self, run_id: UUID):  # type intentionally inferred like the real service
        run = await self.get(run_id)
        if run.status.value != "completed":
            raise BacktestAnalysisUnavailableError(
                "Backtest analysis is available only for completed runs"
            )
        return analyze_backtest_trades(run_id, self.trades.get(run_id, []))

    async def portfolio(self, run_id: UUID):
        from screener.modules.backtest.service import PortfolioUnavailableError

        run = await self.get(run_id)
        if run.status.value != "completed" or run.execution_mode.value != "portfolio":
            raise PortfolioUnavailableError("Portfolio data is unavailable for this run")
        snapshot = PortfolioSnapshot(
            uuid4(),
            run.id,
            date(2026, 1, 2),
            *(
                Decimal(value)
                for value in [
                    "900.00000000",
                    "100.00000000",
                    "0.00000000",
                    "0.00000000",
                    "1000.00000000",
                    "0.00000000",
                    "1000.00000000",
                    "0.00000000",
                    "0.00000000",
                ]
            ),
            1,
        )
        return run, [snapshot]


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
    assert body["result"] == {"entered_trades": 2, "net_profit": "1250.00000000"}

    assert client.get(f"/api/v1/backtests/{body['id']}").json() == body
    assert client.get("/api/v1/backtests").json() == [body]


@pytest.mark.parametrize(
    ("changes", "detail"),
    [
        ({"start_date": "2026-02-01", "end_date": "2026-01-01"}, "start_date"),
        ({"end_date": "2026-03-01"}, "cannot exceed"),
        ({"strategy_name": "other"}, "strategy_name"),
        ({"strategy_version": "2"}, "strategy_version"),
        ({"parameters": {"position_size": 0}}, "position_size"),
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


def trade(run_id: UUID, symbol: str, reason: BacktestExitReason, day: int) -> BacktestTrade:
    return BacktestTrade(
        uuid4(),
        run_id,
        symbol,
        date(2026, 1, day),
        date(2026, 1, day + 1),
        Decimal("100.12345678"),
        10,
        date(2026, 1, day + 2),
        Decimal("110.12345678"),
        reason,
        Decimal("100.00000000"),
        Decimal("1.00000000"),
        Decimal("2.00000000"),
        Decimal("3.00000000"),
        Decimal("94.00000000"),
        1,
    )


def test_trades_endpoint_pagination_and_filters(client: TestClient, service: FakeService) -> None:
    run_id = UUID(client.post("/api/v1/backtests", json=payload()).json()["id"])
    service.trades[run_id] = [
        trade(run_id, "005930", BacktestExitReason.TAKE_PROFIT, 1),
        trade(run_id, "000660", BacktestExitReason.STOP_LOSS, 4),
        trade(run_id, "005930", BacktestExitReason.END_OF_PERIOD, 7),
    ]
    page = client.get(f"/api/v1/backtests/{run_id}/trades?limit=1&offset=1")
    assert page.status_code == 200
    assert [item["symbol"] for item in page.json()] == ["000660"]
    assert page.json()[0]["entry_price"] == "100.12345678"
    by_symbol = client.get(f"/api/v1/backtests/{run_id}/trades?symbol=005930")
    assert [item["symbol"] for item in by_symbol.json()] == ["005930", "005930"]
    by_reason = client.get(f"/api/v1/backtests/{run_id}/trades?exit_reason=stop_loss")
    assert [item["exit_reason"] for item in by_reason.json()] == ["stop_loss"]


def test_unknown_run_trades_return_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/backtests/{uuid4()}/trades")
    assert response.status_code == 404
    assert response.json() == {"detail": "Backtest run not found"}


@pytest.mark.parametrize("query", ["limit=0", "limit=501", "offset=-1", "exit_reason=not_a_reason"])
def test_invalid_trade_query_parameters_return_422(client: TestClient, query: str) -> None:
    assert client.get(f"/api/v1/backtests/{uuid4()}/trades?{query}").status_code == 422


def test_openapi_contains_all_backtest_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"get", "post"} <= set(paths["/api/v1/backtests"])
    assert "get" in paths["/api/v1/backtests/{run_id}"]
    assert "get" in paths["/api/v1/backtests/{run_id}/trades"]
    assert "get" in paths["/api/v1/backtests/{run_id}/analysis"]
    assert "get" in paths["/api/v1/backtests/{run_id}/portfolio"]


def test_portfolio_create_and_exact_response(client: TestClient, service: FakeService) -> None:
    request = payload() | {
        "execution_mode": "portfolio",
        "parameters": {
            "initial_capital": "1000",
            "max_open_positions": 2,
            "position_sizing_mode": "fixed_fraction",
            "position_size_pct": "0.5",
            "minimum_cash_buffer_pct": "0.1",
        },
    }
    created = client.post("/api/v1/backtests", json=request)
    assert created.status_code == 201 and created.json()["execution_mode"] == "portfolio"
    run_id = UUID(created.json()["id"])
    run = service.runs[run_id]
    service.runs[run_id] = replace(
        run,
        result={
            "initial_capital": "1000.00000000",
            "final_equity": "1000.00000000",
            "final_cash": "1000.00000000",
            "net_profit": "0.00000000",
            "total_return": "0.00000000",
            "max_drawdown": "0.00000000",
            "max_drawdown_pct": "0.00000000",
            "maximum_open_positions_used": 1,
            "average_capital_utilization": "0.10000000",
        },
    )
    response = client.get(f"/api/v1/backtests/{run_id}/portfolio")
    assert response.status_code == 200
    assert response.json()["snapshots"][0]["cash"] == "900.00000000"


def test_completed_analysis_serializes_exact_decimal_strings(
    client: TestClient, service: FakeService
) -> None:
    run_id = UUID(client.post("/api/v1/backtests", json=payload()).json()["id"])
    service.trades[run_id] = [trade(run_id, "005930", BacktestExitReason.TAKE_PROFIT, 1)]
    response = client.get(f"/api/v1/backtests/{run_id}/analysis")
    assert response.status_code == 200
    assert response.json()["summary"]["net_profit"] == "94.00000000"
    assert response.json()["cumulative_realized_pnl"][0]["net_pnl"] == "94.00000000"


def test_completed_zero_trade_analysis_is_valid(client: TestClient) -> None:
    run_id = client.post("/api/v1/backtests", json=payload()).json()["id"]
    body = client.get(f"/api/v1/backtests/{run_id}/analysis").json()
    assert body["trade_count"] == 0
    assert body["summary"]["win_rate"] is None
    assert body["cumulative_realized_pnl"] == []


def test_missing_analysis_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/backtests/{uuid4()}/analysis")
    assert response.status_code == 404
    assert response.json() == {"detail": "Backtest run not found"}


@pytest.mark.parametrize("run_status", ["pending", "running", "failed"])
def test_non_completed_analysis_returns_stable_409(
    client: TestClient, service: FakeService, run_status: str
) -> None:
    candidate = BacktestRun.create("watchlist_entry", date(2026, 1, 1), date(2026, 1, 2))
    if run_status in {"running", "failed"}:
        candidate = candidate.start()
    if run_status == "failed":
        candidate = candidate.fail("failure")
    service.runs[candidate.id] = candidate
    response = client.get(f"/api/v1/backtests/{candidate.id}/analysis")
    assert response.status_code == 409
    assert response.json() == {"detail": "Backtest analysis is available only for completed runs"}


@pytest.mark.parametrize("version", [None, "1"])
def test_supported_strategy_versions_succeed(client: TestClient, version: str | None) -> None:
    response = client.post("/api/v1/backtests", json=payload() | {"strategy_version": version})
    assert response.status_code == 201
