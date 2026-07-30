import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from pytest import MonkeyPatch

from screener.modules.market.domain import (
    ProviderAuthenticationError,
    ProviderMalformedResponseError,
    ProviderValidationError,
)
from screener.modules.market.infrastructure.toss import (
    IssuedToken,
    TokenManager,
    TossMarketDataProvider,
    _retry_after,
    issue_token,
)


@pytest.mark.asyncio
async def test_oauth_form_validation_and_cache() -> None:
    calls = 0

    def transport(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/oauth2/token"
        assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
        assert request.content == b"grant_type=client_credentials&client_id=id&client_secret=secret"
        return httpx.Response(
            200, json={"access_token": "private", "token_type": "Bearer", "expires_in": 3600}
        )

    async with httpx.AsyncClient(
        base_url="https://mock", transport=httpx.MockTransport(transport)
    ) as client:
        manager = TokenManager(client, "id", "secret")
        assert await asyncio.gather(*(manager.get() for _ in range(10))) == ["private"] * 10
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"access_token": "", "token_type": "Bearer", "expires_in": 1},
        {"access_token": "x", "token_type": "Basic", "expires_in": 1},
        {"access_token": "x", "token_type": "Bearer", "expires_in": 0},
    ],
)
async def test_malformed_oauth(payload: dict[str, object]) -> None:
    async with httpx.AsyncClient(
        base_url="https://mock",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    ) as client:
        with pytest.raises(ProviderMalformedResponseError):
            await issue_token(client, "id", "secret")


@pytest.mark.asyncio
async def test_401_invalidates_once_and_retries_once() -> None:
    issued = 0
    requests = 0

    async def issuer(_client: httpx.AsyncClient, _id: str, _secret: str) -> IssuedToken:
        nonlocal issued
        issued += 1
        return IssuedToken(access_token=f"t{issued}", token_type="Bearer", expires_in=3600)

    def transport(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(401)

    async with httpx.AsyncClient(
        base_url="https://mock", transport=httpx.MockTransport(transport)
    ) as client:
        provider = TossMarketDataProvider(
            client, TokenManager(client, "id", "secret", issuer), max_retries=0
        )
        with pytest.raises(ProviderAuthenticationError):
            await provider.prices(["005930"])
    assert (issued, requests) == (2, 2)


@pytest.mark.asyncio
async def test_candles_map_sort_decimal_and_request_contract() -> None:
    async def issuer(_client: httpx.AsyncClient, _id: str, _secret: str) -> IssuedToken:
        return IssuedToken(access_token="token", token_type="Bearer", expires_in=3600)

    def transport(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/candles"
        assert request.url.params["symbol"] == "005930"
        assert request.url.params["interval"] == "1d"
        assert request.url.params["count"] == "200"
        assert request.url.params["adjusted"] == "true"
        return httpx.Response(
            200,
            json={
                "result": {
                    "candles": [
                        candle("2026-01-03T00:00:00+09:00", "2", "3", "1", "2.5", "20"),
                        candle("2026-01-02T00:00:00+09:00", "1", "2", "1", "2", "10"),
                    ],
                    "nextBefore": None,
                }
            },
        )

    async with httpx.AsyncClient(
        base_url="https://mock", transport=httpx.MockTransport(transport)
    ) as client:
        provider = TossMarketDataProvider(client, TokenManager(client, "id", "secret", issuer))
        bars = await provider.daily_bars("005930", date(2026, 1, 1), date(2026, 1, 3))
    assert [bar.trading_date for bar in bars] == [date(2026, 1, 2), date(2026, 1, 3)]
    assert bars[1].close == Decimal("2.5")
    assert bars[0].as_of.utcoffset() is not None


@pytest.mark.asyncio
async def test_candle_pages_deduplicate_inclusive_boundary_and_reject_cursor_loop() -> None:
    calls = 0

    def transport(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            rows = [candle("2026-01-03T00:00:00+09:00"), candle("2026-01-02T00:00:00+09:00")]
            cursor = "2026-01-02T00:00:00+09:00"
        else:
            rows = [candle("2026-01-02T00:00:00+09:00"), candle("2026-01-01T00:00:00+09:00")]
            cursor = None
        return httpx.Response(200, json={"result": {"candles": rows, "nextBefore": cursor}})

    async with httpx.AsyncClient(
        base_url="https://mock", transport=httpx.MockTransport(transport)
    ) as client:
        provider = TossMarketDataProvider(client, TokenManager(client, "id", "secret", issuer))
        bars = await provider.daily_bars("005930", date(2026, 1, 1), date(2026, 1, 3))
    assert calls == 2
    assert [bar.trading_date for bar in bars] == [
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 3),
    ]


@pytest.mark.asyncio
async def test_nested_common_and_flat_oauth_errors_preserve_diagnostics() -> None:
    async with httpx.AsyncClient(
        base_url="https://mock",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                400,
                json={
                    "error": {
                        "requestId": "request-1",
                        "code": "INVALID_SYMBOL",
                        "message": "bad symbol",
                    }
                },
            )
        ),
    ) as client:
        provider = TossMarketDataProvider(client, TokenManager(client, "id", "secret", issuer))
        with pytest.raises(ProviderValidationError) as caught:
            await provider.instrument("005930")
    assert (caught.value.provider_code, caught.value.request_id, caught.value.provider_message) == (
        "INVALID_SYMBOL",
        "request-1",
        "bad symbol",
    )

    async with httpx.AsyncClient(
        base_url="https://mock",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                401, json={"error": "invalid_client", "error_description": "credentials rejected"}
            )
        ),
    ) as client:
        with pytest.raises(ProviderAuthenticationError) as oauth:
            await issue_token(client, "id", "secret")
    assert oauth.value.provider_code == "invalid_client"
    assert oauth.value.provider_message == "credentials rejected"


@pytest.mark.asyncio
async def test_stock_master_batches_200_and_maps_and_filters_official_fields(
    monkeypatch: MonkeyPatch,
) -> None:
    symbols = [f"{value:06d}" for value in range(201)]
    monkeypatch.setattr(
        "screener.modules.market.infrastructure.toss.load_kospi_symbols", lambda: symbols
    )
    batch_sizes: list[int] = []

    def transport(request: httpx.Request) -> httpx.Response:
        requested = request.url.params["symbols"].split(",")
        batch_sizes.append(len(requested))
        assert set(request.url.params) == {"symbols"}
        rows = [stock(symbol) for symbol in requested]
        if "000200" in requested:
            rows[-1]["isCommonShare"] = False
        return httpx.Response(200, json={"result": rows})

    async with httpx.AsyncClient(
        base_url="https://mock", transport=httpx.MockTransport(transport)
    ) as client:
        provider = TossMarketDataProvider(client, TokenManager(client, "id", "secret", issuer))
        stocks = await provider.stock_master()
    assert batch_sizes == [200, 1]
    assert len(stocks) == 200
    assert stocks[0].list_date == date(1975, 6, 11)
    assert stocks[0].korean_market_detail == "KOSPI"


def test_retry_after_malformed_is_safe() -> None:
    assert _retry_after("not-a-date") == 0.1
    assert 0 <= _retry_after(email_date(datetime.now(UTC))) <= 30


def email_date(value: datetime) -> str:
    return value.strftime("%a, %d %b %Y %H:%M:%S GMT")


async def issuer(_client: httpx.AsyncClient, _id: str, _secret: str) -> IssuedToken:
    return IssuedToken(access_token="token", token_type="Bearer", expires_in=3600)


def candle(
    timestamp: str,
    open_price: str = "1",
    high: str = "2",
    low: str = "1",
    close: str = "2",
    volume: str = "10",
) -> dict[str, str]:
    return {
        "timestamp": timestamp,
        "openPrice": open_price,
        "highPrice": high,
        "lowPrice": low,
        "closePrice": close,
        "volume": volume,
        "currency": "KRW",
    }


def stock(symbol: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "name": f"stock-{symbol}",
        "market": "KOSPI",
        "currency": "KRW",
        "securityType": "STOCK",
        "isCommonShare": True,
        "status": "ACTIVE",
        "listDate": "1975-06-11",
        "delistDate": None,
        "koreanMarketDetail": "KOSPI",
    }
