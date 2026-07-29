"""Contract tests for the read-only watchlist REST API."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from screener.api.watchlist.dependencies import get_watchlist_repository
from screener.main import app
from screener.modules.market.screening import ScreeningResult
from screener.modules.market.watchlist import WatchlistEntry


def entry(symbol: str = "005930", trading_date: date = date(2026, 7, 28)) -> WatchlistEntry:
    return WatchlistEntry(
        id=uuid4(),
        trading_date=trading_date,
        symbol=symbol,
        rank=1,
        total_score=Decimal("91.12345678901234567890123456789"),
        component_scores={"trend": Decimal("87.12345678901234567890123456789")},
        warnings=["ranking warning"],
        snapshot=ScreeningResult(
            symbol=symbol,
            passed=True,
            metrics={"atr": Decimal("0.12345678901234567890123456789")},
            reasons=["PASSED: test reason"],
            warnings=["screening warning"],
        ),
    )


class FakeRepository:
    def __init__(
        self,
        entries: list[WatchlistEntry] | None = None,
        successful_dates: set[date] | None = None,
    ) -> None:
        self.entries = entries or []
        self.successful_dates = successful_dates or set()

    async def latest(self) -> list[WatchlistEntry]:
        return self.entries

    async def history(self) -> list[date]:
        return [date(2026, 7, 28), date(2026, 7, 27), date(2026, 7, 24)]

    async def list(self, trading_date: date) -> list[WatchlistEntry]:
        return [item for item in self.entries if item.trading_date == trading_date]

    async def get(self, trading_date: date, symbol: str) -> WatchlistEntry | None:
        return next(
            (
                item
                for item in self.entries
                if item.trading_date == trading_date and item.symbol == symbol
            ),
            None,
        )

    async def has_successful_execution(self, trading_date: date) -> bool:
        return trading_date in self.successful_dates


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()


def use_repository(repository: FakeRepository) -> None:
    app.dependency_overrides[get_watchlist_repository] = lambda: repository


def test_latest_empty(client: TestClient) -> None:
    use_repository(FakeRepository())
    response = client.get("/api/v1/watchlist/latest")
    assert response.status_code == 200
    assert response.json() == []


def test_latest_populated_and_hides_internal_fields(client: TestClient) -> None:
    use_repository(FakeRepository([entry()]))
    response = client.get("/api/v1/watchlist/latest")
    assert response.status_code == 200
    assert response.json()[0]["symbol"] == "005930"
    assert "id" not in response.json()[0]
    assert "trading_date" not in response.json()[0]


def test_history_is_newest_first(client: TestClient) -> None:
    use_repository(FakeRepository())
    response = client.get("/api/v1/watchlist/history")
    assert response.status_code == 200
    assert response.json() == ["2026-07-28", "2026-07-27", "2026-07-24"]


def test_get_date(client: TestClient) -> None:
    use_repository(FakeRepository([entry()]))
    response = client.get("/api/v1/watchlist/2026-07-28")
    assert response.status_code == 200
    assert response.json()[0]["rank"] == 1


def test_missing_date(client: TestClient) -> None:
    use_repository(FakeRepository())
    response = client.get("/api/v1/watchlist/2026-07-28")
    assert response.status_code == 404


def test_successful_empty_date_returns_200(client: TestClient) -> None:
    day = date(2026, 7, 28)
    use_repository(FakeRepository(successful_dates={day}))
    response = client.get(f"/api/v1/watchlist/{day}")
    assert response.status_code == 200
    assert response.json() == []


def test_get_symbol_returns_inspection_fields(client: TestClient) -> None:
    use_repository(FakeRepository([entry()]))
    response = client.get("/api/v1/watchlist/2026-07-28/005930")
    assert response.status_code == 200
    assert response.json()["trading_date"] == "2026-07-28"
    assert response.json()["metrics"]["atr"] == "0.12345678901234567890123456789"
    assert response.json()["reasons"] == ["PASSED: test reason"]
    assert response.json()["warnings"] == ["ranking warning"]


def test_missing_symbol(client: TestClient) -> None:
    use_repository(FakeRepository([entry()]))
    response = client.get("/api/v1/watchlist/2026-07-28/MISSING")
    assert response.status_code == 404


def test_invalid_date_format(client: TestClient) -> None:
    use_repository(FakeRepository())
    response = client.get("/api/v1/watchlist/not-a-date")
    assert response.status_code == 422


def test_decimal_serialization_never_uses_float(client: TestClient) -> None:
    use_repository(FakeRepository([entry()]))
    item = client.get("/api/v1/watchlist/latest").json()[0]
    assert item["total_score"] == "91.12345678901234567890123456789"
    assert item["component_scores"]["trend"] == "87.12345678901234567890123456789"
    assert isinstance(item["total_score"], str)


def test_snapshot_returned_only_by_detail_endpoint(client: TestClient) -> None:
    use_repository(FakeRepository([entry()]))
    latest = client.get("/api/v1/watchlist/latest").json()[0]
    dated = client.get("/api/v1/watchlist/2026-07-28").json()[0]
    detail = client.get("/api/v1/watchlist/2026-07-28/005930").json()
    assert "snapshot" not in latest
    assert "snapshot" not in dated
    assert detail["snapshot"]["symbol"] == "005930"


def test_repository_exception_returns_500(client: TestClient) -> None:
    repository = FakeRepository()

    async def fail() -> list[WatchlistEntry]:
        raise RuntimeError("database details must not leak")

    repository.latest = fail  # type: ignore[method-assign]
    use_repository(repository)
    response = client.get("/api/v1/watchlist/latest")
    assert response.status_code == 500
    assert response.json() == {"detail": "Watchlist repository error"}


def test_openapi_generation_documents_watchlist_routes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/v1/watchlist/latest" in schema["paths"]
    assert "/api/v1/watchlist/history" in schema["paths"]
    assert "/api/v1/watchlist/{trading_date}" in schema["paths"]
    assert "/api/v1/watchlist/{trading_date}/{symbol}" in schema["paths"]
