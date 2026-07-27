from datetime import UTC, date, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from screener.main import app
from screener.modules.identity.presentation.dependencies import get_current_user
from screener.modules.market.application import MarketDataService
from screener.modules.market.domain import DailyBar, ProviderState, ProviderStatus
from screener.modules.market.presentation.router import get_market_data_service


class FakeProvider:
    async def status(self) -> ProviderStatus:
        return ProviderStatus(
            provider="mock", state=ProviderState.AVAILABLE, as_of=datetime.now(UTC)
        )

    async def instrument(self, symbol: str):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def daily_bars(self, symbol: str, start: date, end: date) -> list[DailyBar]:
        return [
            DailyBar(
                symbol=symbol,
                trading_date=start,
                open=1,
                high=2,
                low=1,
                close=2,
                volume=10,
                source="mock",
                as_of=datetime.now(UTC),
            )
        ]


def test_market_api_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/operations/providers/market-data")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired credentials"


def test_bars_response_contains_metadata() -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
    app.dependency_overrides[get_market_data_service] = lambda: MarketDataService(FakeProvider())
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/instruments/005930/bars",
                params={"start_date": "2026-01-02", "end_date": "2026-01-03"},
            )
        assert response.status_code == 200
        assert response.json()["source"] == "mock"
        assert response.json()["timezone"] == "Asia/Seoul"
        assert isinstance(response.json()["stale"], bool)
    finally:
        app.dependency_overrides.clear()
