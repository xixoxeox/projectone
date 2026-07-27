import asyncio
from datetime import date, datetime
from decimal import Decimal

import httpx
import pytest

from screener.modules.market.domain import (
    DailyBar,
    ProviderAuthenticationError,
    ProviderMalformedResponseError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    ProviderValidationError,
)
from screener.modules.market.infrastructure.toss import (
    IssuedToken,
    TokenManager,
    TossApiSpecification,
    TossMarketDataProvider,
)


def specification() -> TossApiSpecification:
    def map_bar(row: dict[str, object], symbol: str, as_of: datetime) -> DailyBar:
        return DailyBar(
            symbol=symbol,
            trading_date=date.fromisoformat(str(row["date"])),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=int(str(row["volume"])),
            source="toss",
            as_of=as_of,
        )

    return TossApiSpecification(
        lambda symbol: f"/bars/{symbol}",
        lambda start, end: {"from": start.isoformat(), "to": end.isoformat()},
        map_bar,
        lambda payload: payload["items"],
    )  # type: ignore[return-value]


async def manager(client: httpx.AsyncClient, issuer=None, skew: int = 30) -> TokenManager:
    async def default_issuer(
        _client: httpx.AsyncClient, client_id: str, secret: str
    ) -> IssuedToken:
        assert (client_id, secret) == ("id", "secret")
        return IssuedToken(access_token="private-token", expires_in=3600)

    return TokenManager(client, "id", "secret", issuer or default_issuer, skew)


@pytest.mark.asyncio
async def test_token_is_issued_cached_and_concurrent_refresh_is_coalesced() -> None:
    calls = 0

    async def issuer(_client: httpx.AsyncClient, _id: str, _secret: str) -> IssuedToken:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return IssuedToken(access_token="token", expires_in=3600)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200))
    ) as client:
        tokens = await manager(client, issuer)
        assert await asyncio.gather(*(tokens.get() for _ in range(10))) == ["token"] * 10
        assert await tokens.get() == "token"
    assert calls == 1


@pytest.mark.asyncio
async def test_token_reissued_inside_expiry_skew() -> None:
    calls = 0

    async def issuer(_client: httpx.AsyncClient, _id: str, _secret: str) -> IssuedToken:
        nonlocal calls
        calls += 1
        return IssuedToken(access_token=f"token-{calls}", expires_in=1)

    async with httpx.AsyncClient() as client:
        tokens = await manager(client, issuer, skew=30)
        assert await tokens.get() == "token-1"
        assert await tokens.get() == "token-2"


@pytest.mark.asyncio
async def test_successful_mapping_and_authorization_is_not_returned() -> None:
    def transport(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer private-token"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "date": "2026-01-02",
                        "open": "1",
                        "high": "3",
                        "low": "1",
                        "close": "2",
                        "volume": 10,
                    }
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(transport), base_url="https://mock"
    ) as client:
        provider = TossMarketDataProvider(client, await manager(client), specification())
        bars = await provider.daily_bars("005930", date(2026, 1, 1), date(2026, 1, 2))
    assert bars[0].close == Decimal("2")
    assert "private-token" not in repr(bars)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, ProviderAuthenticationError),
        (403, ProviderAuthenticationError),
        (400, ProviderValidationError),
    ],
)
async def test_permanent_errors_are_normalized_without_retry(
    status: int, error: type[Exception]
) -> None:
    calls = 0

    def transport(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(transport), base_url="https://mock"
    ) as client:
        provider = TossMarketDataProvider(client, await manager(client), specification(), 2)
        with pytest.raises(error):
            await provider.daily_bars("A", date.today(), date.today())
    assert calls == 1


@pytest.mark.asyncio
async def test_5xx_retries_then_succeeds() -> None:
    calls = 0

    def transport(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503 if calls < 3 else 200, json={"items": []})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(transport), base_url="https://mock"
    ) as client:
        provider = TossMarketDataProvider(client, await manager(client), specification(), 2)
        assert await provider.daily_bars("A", date.today(), date.today()) == []
    assert calls == 3


@pytest.mark.asyncio
async def test_timeout_and_rate_limit_are_normalized() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret must not leak", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(timeout), base_url="https://mock"
    ) as client:
        provider = TossMarketDataProvider(client, await manager(client), specification(), 0)
        with pytest.raises(ProviderUnavailableError, match="Provider request failed") as exc:
            await provider.daily_bars("A", date.today(), date.today())
        assert "secret" not in str(exc.value)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": "0"})),
        base_url="https://mock",
    ) as client:
        provider = TossMarketDataProvider(client, await manager(client), specification(), 0)
        with pytest.raises(ProviderRateLimitError):
            await provider.daily_bars("A", date.today(), date.today())


@pytest.mark.asyncio
async def test_malformed_response_is_rejected() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"unexpected": []})),
        base_url="https://mock",
    ) as client:
        provider = TossMarketDataProvider(client, await manager(client), specification())
        with pytest.raises(ProviderMalformedResponseError):
            await provider.daily_bars("A", date.today(), date.today())
