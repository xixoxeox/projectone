from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from screener.main import app
from screener.modules.identity.presentation.dependencies import get_current_user
from screener.modules.market.application import MarketDataService
from screener.modules.market.domain import (
    DailyBar,
    InstrumentSnapshot,
    MinuteBar,
    ProviderState,
    ProviderStatus,
    QuoteSnapshot,
    StockWarning,
)
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


class AnalysisProvider(FakeProvider):
    async def instrument(self, symbol: str) -> InstrumentSnapshot:
        return InstrumentSnapshot(
            symbol=symbol,
            name="삼성전자",
            market="KOSPI",
            currency="KRW",
            security_type="common_stock",
            listing_status="listed",
            source="mock",
            as_of=datetime.now(UTC),
        )

    async def daily_bars(self, symbol: str, start: date, end: date) -> list[DailyBar]:
        return [
            DailyBar(
                symbol=symbol,
                trading_date=end - timedelta(days=79 - index),
                open=Decimal("70000") + index,
                high=Decimal("70200") + index,
                low=Decimal("69900") + index,
                close=Decimal("70100") + index,
                volume=200_000,
                source="mock",
                as_of=datetime.now(UTC),
            )
            for index in range(80)
        ]

    async def minute_bars(self, symbol: str, count: int = 200) -> list[MinuteBar]:
        now = datetime.now(ZoneInfo("Asia/Seoul")).replace(second=0, microsecond=0)
        return [
            MinuteBar(
                symbol=symbol,
                timestamp=now - timedelta(minutes=39 - index),
                open=Decimal("70100") + index,
                high=Decimal("70120") + index,
                low=Decimal("70090") + index,
                close=Decimal("70110") + index,
                volume=1_000 + index,
                currency="KRW",
                source="mock",
                as_of=now - timedelta(minutes=39 - index),
            )
            for index in range(40)
        ]

    async def prices(self, symbols: list[str]) -> list[QuoteSnapshot]:
        return [
            QuoteSnapshot(
                symbol=symbols[0],
                price=Decimal("70200"),
                currency="KRW",
                source="mock",
                as_of=datetime.now(UTC),
                delayed=False,
            )
        ]

    async def warnings(self, symbol: str) -> list[StockWarning]:
        return []


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


def test_individual_analysis_returns_chart_ready_timeframes_and_threshold() -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
    app.dependency_overrides[get_market_data_service] = lambda: MarketDataService(
        AnalysisProvider()
    )
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/instruments/005930/analysis")

        assert response.status_code == 200
        payload = response.json()
        assert payload["instrument"]["name"] == "삼성전자"
        assert set(payload["intraday_bars"]) == {"1m", "5m", "10m"}
        assert payload["daily"]["score_threshold"] == "80"
        assert payload["refresh_after_seconds"] == 60
    finally:
        app.dependency_overrides.clear()
