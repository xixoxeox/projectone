import asyncio
import email.utils
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from screener.modules.market.domain import (
    DailyBar,
    InstrumentSnapshot,
    ProviderAuthenticationError,
    ProviderMalformedResponseError,
    ProviderRateLimitError,
    ProviderState,
    ProviderStatus,
    ProviderUnavailableError,
    ProviderValidationError,
)

PROVIDER = "toss"


class IssuedToken(BaseModel):
    access_token: str
    expires_in: int


TokenIssuer = Callable[[httpx.AsyncClient, str, str], Awaitable[IssuedToken]]


class TokenManager:
    """In-memory token cache; issuer mapping stays isolated from provider-neutral code."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        client_id: str,
        client_secret: str,
        issuer: TokenIssuer,
        skew_seconds: int = 30,
    ) -> None:
        self._client = client
        self._client_id = client_id
        self._client_secret = client_secret
        self._issuer = issuer
        self._skew = timedelta(seconds=skew_seconds)
        self._token: str | None = None
        self._expires_at = datetime.min.replace(tzinfo=UTC)
        self._lock = asyncio.Lock()

    async def get(self) -> str:
        if self._token is not None and datetime.now(UTC) + self._skew < self._expires_at:
            return self._token
        async with self._lock:
            if self._token is not None and datetime.now(UTC) + self._skew < self._expires_at:
                return self._token
            issued = await self._issuer(self._client, self._client_id, self._client_secret)
            self._token = issued.access_token
            self._expires_at = datetime.now(UTC) + timedelta(seconds=issued.expires_in)
            return self._token


@dataclass(frozen=True)
class TossApiSpecification:
    """Verified paths and mappings. No defaults exist because the official spec is unavailable."""

    bars_path: Callable[[str], str]
    bars_params: Callable[[date, date], dict[str, str]]
    map_bar: Callable[[dict[str, Any], str, datetime], DailyBar]
    extract_bars: Callable[[dict[str, Any]], list[dict[str, Any]]]


class TossMarketDataProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        token_manager: TokenManager | None,
        specification: TossApiSpecification | None,
        max_retries: int = 2,
    ) -> None:
        self._client = client
        self._tokens = token_manager
        self._spec = specification
        self._max_retries = max_retries

    async def status(self) -> ProviderStatus:
        configured = self._tokens is not None and self._spec is not None
        return ProviderStatus(
            provider=PROVIDER,
            state=ProviderState.AVAILABLE if configured else ProviderState.UNAVAILABLE,
            as_of=datetime.now(UTC),
            message=None if configured else "Official Toss API contract is not configured",
        )

    async def instrument(self, symbol: str) -> InstrumentSnapshot:
        del symbol
        raise ProviderUnavailableError("Instrument endpoint is unverified", provider=PROVIDER)

    async def daily_bars(self, symbol: str, start: date, end: date) -> list[DailyBar]:
        if self._tokens is None or self._spec is None:
            raise ProviderUnavailableError(
                "Official Toss bars contract is unverified", provider=PROVIDER
            )
        response = await self._request(
            self._spec.bars_path(symbol), self._spec.bars_params(start, end)
        )
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError
            rows = self._spec.extract_bars(payload)
            as_of = datetime.now(UTC)
            return [self._spec.map_bar(row, symbol, as_of) for row in rows]
        except (ValueError, TypeError, KeyError, ValidationError) as exc:
            raise ProviderMalformedResponseError(
                "Malformed provider response", provider=PROVIDER
            ) from exc

    async def _request(self, path: str, params: dict[str, str]) -> httpx.Response:
        assert self._tokens is not None
        for attempt in range(self._max_retries + 1):
            token = await self._tokens.get()
            try:
                response = await self._client.get(
                    path, params=params, headers={"Authorization": f"Bearer {token}"}
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == self._max_retries:
                    raise ProviderUnavailableError(
                        "Provider request failed", provider=PROVIDER, retryable=True
                    ) from exc
                continue
            if response.status_code < 400:
                return response
            if response.status_code in (401, 403):
                raise ProviderAuthenticationError(
                    "Provider authentication failed", provider=PROVIDER
                )
            if response.status_code == 429:
                if attempt == self._max_retries:
                    raise ProviderRateLimitError(
                        "Provider rate limit exceeded", provider=PROVIDER, retryable=True
                    )
                await asyncio.sleep(_retry_after(response.headers.get("Retry-After")))
                continue
            if 500 <= response.status_code < 600:
                if attempt < self._max_retries:
                    await asyncio.sleep(min(0.1 * (2**attempt), 1.0))
                    continue
                raise ProviderUnavailableError(
                    "Provider is unavailable", provider=PROVIDER, retryable=True
                )
            raise ProviderValidationError("Provider rejected the request", provider=PROVIDER)
        raise AssertionError("unreachable")


def _retry_after(value: str | None) -> float:
    if value is None:
        return 0.1
    try:
        return max(0.0, min(float(value), 30.0))
    except ValueError:
        parsed = email.utils.parsedate_to_datetime(value)
        return max(0.0, min((parsed - datetime.now(UTC)).total_seconds(), 30.0))
