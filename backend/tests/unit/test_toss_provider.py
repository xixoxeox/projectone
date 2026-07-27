import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from screener.modules.market.domain import (
    ProviderAuthenticationError,
    ProviderMalformedResponseError,
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
        return httpx.Response(
            200,
            json={
                "candles": [
                    {
                        "timestamp": "2026-01-03T00:00:00+09:00",
                        "open": "2",
                        "high": "3",
                        "low": "1",
                        "close": "2.5",
                        "volume": 20,
                    },
                    {
                        "timestamp": "2026-01-02T00:00:00+09:00",
                        "open": "1",
                        "high": "2",
                        "low": "1",
                        "close": "2",
                        "volume": 10,
                    },
                ]
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


def test_retry_after_malformed_is_safe() -> None:
    assert _retry_after("not-a-date") == 0.1
    assert 0 <= _retry_after(email_date(datetime.now(UTC))) <= 30


def email_date(value: datetime) -> str:
    return value.strftime("%a, %d %b %Y %H:%M:%S GMT")
