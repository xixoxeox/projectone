import asyncio
import email.utils
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Never
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from screener.modules.market.domain import (
    DailyBar,
    InstrumentSnapshot,
    ProviderAuthenticationError,
    ProviderForbiddenError,
    ProviderMalformedResponseError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderState,
    ProviderStatus,
    ProviderUnavailableError,
    ProviderValidationError,
    QuoteSnapshot,
    StockWarning,
)
from screener.modules.market.infrastructure.universe import load_kospi_symbols

PROVIDER = "toss"


class IssuedToken(BaseModel):
    model_config = ConfigDict(extra="ignore")
    access_token: str = Field(min_length=1)
    token_type: str = "Bearer"
    expires_in: int = Field(gt=0)

    @field_validator("access_token")
    @classmethod
    def token_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("empty access token")
        return value

    @field_validator("token_type")
    @classmethod
    def bearer_only(cls, value: str) -> str:
        if value.casefold() != "bearer":
            raise ValueError("unsupported token type")
        return value


class TossCommonError(BaseModel):
    model_config = ConfigDict(extra="ignore")
    requestId: str | None = None
    code: str | None = None
    message: str | None = None


class TossErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")
    error: TossCommonError


class OAuthErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")
    error: str | None = None
    error_description: str | None = None


TokenIssuer = Callable[[httpx.AsyncClient, str, str], Awaitable[IssuedToken]]


async def issue_token(client: httpx.AsyncClient, client_id: str, secret: str) -> IssuedToken:
    try:
        response = await client.post(
            "/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise ProviderUnavailableError(
            "Token service request failed", provider=PROVIDER, retryable=True
        ) from exc
    if response.status_code >= 400:
        _raise_response_error(response, authentication=True)
    try:
        return IssuedToken.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        raise ProviderMalformedResponseError("Malformed token response", provider=PROVIDER) from exc


class TokenManager:
    """One process-scoped token cache with refresh and invalidation coalescing."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        client_id: str,
        client_secret: str,
        issuer: TokenIssuer = issue_token,
        skew_seconds: int = 30,
    ) -> None:
        self._client, self._client_id, self._client_secret = client, client_id, client_secret
        self._issuer, self._skew = issuer, timedelta(seconds=skew_seconds)
        self._token: str | None = None
        self._expires_at = datetime.min.replace(tzinfo=UTC)
        self._lock = asyncio.Lock()

    async def get(self) -> str:
        if self._valid():
            return self._token or ""
        async with self._lock:
            if self._valid():
                return self._token or ""
            issued = await self._issuer(self._client, self._client_id, self._client_secret)
            self._token = issued.access_token
            self._expires_at = datetime.now(UTC) + timedelta(seconds=issued.expires_in)
            return self._token

    async def invalidate(self, rejected_token: str) -> None:
        """Only discard the token which actually received 401 (prevents refresh storms)."""
        async with self._lock:
            if self._token == rejected_token:
                self._token = None
                self._expires_at = datetime.min.replace(tzinfo=UTC)

    def _valid(self) -> bool:
        return self._token is not None and datetime.now(UTC) + self._skew < self._expires_at


class TossApiSpecification:
    """OpenAPI 1.2.5 contract constants, kept entirely at the adapter boundary."""

    VERSION = "1.2.5"
    TOKEN_PATH = "/oauth2/token"
    CANDLES_PATH = "/api/v1/candles"
    PRICES_PATH = "/api/v1/prices"
    STOCKS_PATH = "/api/v1/stocks"
    WARNINGS_PATH = "/api/v1/stocks/{symbol}/warnings"
    DAILY_INTERVAL = "1d"
    MAX_CANDLES = 200
    MAX_STOCK_SYMBOLS = 200
    MAX_PRICE_SYMBOLS = 100
    CHART_REQUEST_INTERVAL_SECONDS = 0.21


class TossMarketDataProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        token_manager: TokenManager | None,
        specification: TossApiSpecification | None = None,
        max_retries: int = 2,
    ) -> None:
        self._client, self._tokens = client, token_manager
        self._spec = specification or TossApiSpecification()
        self._max_retries = max_retries
        self._last_success: datetime | None = None
        self._last_failure: datetime | None = None
        self._chart_lock = asyncio.Lock()
        self._last_chart_request = 0.0

    async def status(self) -> ProviderStatus:
        configured = self._tokens is not None
        state = (
            ProviderState.UNCONFIGURED
            if not configured
            else (
                ProviderState.DEGRADED
                if self._last_failure
                and (not self._last_success or self._last_failure > self._last_success)
                else ProviderState.AVAILABLE
            )
        )
        return ProviderStatus(
            provider=PROVIDER,
            configured=configured,
            state=state,
            as_of=datetime.now(UTC),
            api_base_host=urlparse(str(self._client.base_url)).hostname,
            api_version=self._spec.VERSION,
            message=None if configured else "Toss client credentials are not configured",
            last_successful_request_at=self._last_success,
        )

    async def instrument(self, symbol: str) -> InstrumentSnapshot:
        response = await self._request(self._spec.STOCKS_PATH, {"symbols": symbol})
        rows = self._result_rows(response)
        matches = [row for row in rows if str(row.get("symbol", "")) == symbol]
        if not matches:
            raise ProviderNotFoundError("Instrument not found", provider=PROVIDER)
        if len(matches) != 1:
            self._malformed()
        row = matches[0]
        try:
            return self._instrument(row, datetime.now(UTC))
        except (KeyError, TypeError, ValidationError) as exc:
            self._malformed(exc)

    async def stock_master(self, market: str = "KOSPI") -> list[InstrumentSnapshot]:
        """Enrich the reviewed KRX snapshot in official 200-symbol batches."""
        if market != "KOSPI":
            raise ProviderValidationError("Unsupported stock universe", provider=PROVIDER)
        symbols = load_kospi_symbols()
        result: list[InstrumentSnapshot] = []
        for offset in range(0, len(symbols), self._spec.MAX_STOCK_SYMBOLS):
            batch = symbols[offset : offset + self._spec.MAX_STOCK_SYMBOLS]
            response = await self._request(self._spec.STOCKS_PATH, {"symbols": ",".join(batch)})
            try:
                now = datetime.now(UTC)
                result.extend(self._instrument(row, now) for row in self._result_rows(response))
            except (KeyError, TypeError, ValidationError) as exc:
                self._malformed(exc)
        requested = set(symbols)
        return [
            item
            for item in result
            if item.symbol in requested
            and item.market == "KOSPI"
            and item.security_type == "common_stock"
            and item.is_common_share is True
            and item.listing_status == "listed"
        ]

    async def daily_bars(self, symbol: str, start: date, end: date) -> list[DailyBar]:
        if start > end:
            raise ProviderValidationError("Invalid candle date range", provider=PROVIDER)
        before: str | None = datetime.combine(
            end, datetime.max.time(), tzinfo=ZoneInfo("Asia/Seoul")
        ).isoformat()
        cursors: set[str] = set()
        by_date: dict[date, DailyBar] = {}
        while before is not None:
            if before in cursors:
                self._malformed()
            cursors.add(before)
            response = await self._request(
                self._spec.CANDLES_PATH,
                {
                    "symbol": symbol,
                    "interval": self._spec.DAILY_INTERVAL,
                    "count": str(self._spec.MAX_CANDLES),
                    "before": before,
                    "adjusted": "true",
                },
                chart=True,
            )
            payload = self._result_object(response)
            rows = self._rows(payload, "candles")
            try:
                for row in rows:
                    timestamp = _parse_datetime(row["timestamp"])
                    trading_date = timestamp.date()
                    bar = DailyBar(
                        symbol=symbol,
                        trading_date=trading_date,
                        open=_decimal(row["openPrice"]),
                        high=_decimal(row["highPrice"]),
                        low=_decimal(row["lowPrice"]),
                        close=_decimal(row["closePrice"]),
                        volume=_integer(row["volume"]),
                        source=PROVIDER,
                        as_of=timestamp,
                    )
                    if start <= trading_date <= end and trading_date <= date.today():
                        existing = by_date.get(trading_date)
                        if existing is not None and existing != bar:
                            self._malformed()
                        by_date[trading_date] = bar
            except (KeyError, TypeError, ValueError, ValidationError, InvalidOperation) as exc:
                self._malformed(exc)
            if rows and min(_parse_datetime(row["timestamp"]).date() for row in rows) <= start:
                break
            value = payload.get("nextBefore")
            before = str(value) if value else None
        return [by_date[value] for value in sorted(by_date)]

    async def prices(self, symbols: list[str]) -> list[QuoteSnapshot]:
        if not 1 <= len(symbols) <= self._spec.MAX_PRICE_SYMBOLS:
            raise ProviderValidationError("Invalid price batch size", provider=PROVIDER)
        if len(set(symbols)) != len(symbols):
            raise ProviderValidationError("Duplicate symbols are not allowed", provider=PROVIDER)
        response = await self._request(self._spec.PRICES_PATH, {"symbols": ",".join(symbols)})
        rows = self._result_rows(response)
        try:
            quotes = [
                QuoteSnapshot(
                    symbol=str(row["symbol"]),
                    price=_decimal(row["lastPrice"]),
                    currency=str(row["currency"]),
                    source=PROVIDER,
                    as_of=_parse_datetime(row["timestamp"]),
                    delayed=_optional_bool(row, "delayed"),
                )
                for row in rows
            ]
        except (KeyError, TypeError, ValueError, ValidationError, InvalidOperation) as exc:
            self._malformed(exc)
        returned = [q.symbol for q in quotes]
        if len(returned) != len(set(returned)) or set(returned) != set(symbols):
            self._malformed()
        return quotes

    async def warnings(self, symbol: str) -> list[StockWarning]:
        response = await self._request(self._spec.WARNINGS_PATH.format(symbol=symbol), {})
        rows = self._result_rows(response)
        try:
            return [
                StockWarning(
                    symbol=symbol,
                    warning_type=str(row["warningType"]),
                    active=_warning_active(row),
                    description=_optional(row, "description"),
                    exchange=_optional(row, "exchange"),
                    start_date=_optional_date(row, "startDate"),
                    end_date=_optional_date(row, "endDate"),
                    source=PROVIDER,
                    as_of=datetime.now(UTC),
                )
                for row in rows
            ]
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            self._malformed(exc)

    async def _request(
        self, path: str, params: dict[str, str], *, chart: bool = False
    ) -> httpx.Response:
        if self._tokens is None:
            raise ProviderUnavailableError("Provider is unconfigured", provider=PROVIDER)
        auth_retried = False
        attempt = 0
        while True:
            token = await self._tokens.get()
            if chart:
                async with self._chart_lock:
                    loop = asyncio.get_running_loop()
                    wait = self._spec.CHART_REQUEST_INTERVAL_SECONDS - (
                        loop.time() - self._last_chart_request
                    )
                    if wait > 0:
                        await asyncio.sleep(wait)
                    self._last_chart_request = loop.time()
            try:
                response = await self._client.get(
                    path, params=params, headers={"Authorization": f"Bearer {token}"}
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self._max_retries:
                    self._last_failure = datetime.now(UTC)
                    raise ProviderUnavailableError(
                        "Provider request failed", provider=PROVIDER, retryable=True
                    ) from exc
                attempt += 1
                await asyncio.sleep(min(0.1 * 2**attempt, 2))
                continue
            if response.status_code == 401 and not auth_retried:
                auth_retried = True
                await self._tokens.invalidate(token)
                continue
            if response.status_code < 400:
                self._last_success = datetime.now(UTC)
                return response
            if response.status_code == 429 and attempt < self._max_retries:
                attempt += 1
                await asyncio.sleep(
                    _retry_after(
                        response.headers.get("Retry-After"),
                        response.headers.get("X-RateLimit-Reset"),
                    )
                )
                continue
            if 500 <= response.status_code < 600 and attempt < self._max_retries:
                attempt += 1
                await asyncio.sleep(min((0.2 if chart else 0.1) * 2**attempt, 2))
                continue
            self._last_failure = datetime.now(UTC)
            _raise_response_error(response)
        raise AssertionError("unreachable")

    @staticmethod
    def _object(response: httpx.Response) -> dict[str, Any]:
        try:
            value = response.json()
            if not isinstance(value, dict):
                raise TypeError
            return value
        except (ValueError, TypeError) as exc:
            TossMarketDataProvider._malformed(exc)

    @classmethod
    def _result_object(cls, response: httpx.Response) -> dict[str, Any]:
        value = cls._object(response).get("result")
        if not isinstance(value, dict):
            cls._malformed()
        return value

    @classmethod
    def _result_rows(cls, response: httpx.Response) -> list[dict[str, Any]]:
        value = cls._object(response).get("result")
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            cls._malformed()
        return value

    @staticmethod
    def _instrument(row: dict[str, Any], as_of: datetime) -> InstrumentSnapshot:
        detail = row.get("koreanMarketDetail")
        is_active_common_stock = (
            row.get("market") == "KOSPI"
            and row.get("securityType") == "STOCK"
            and row.get("isCommonShare") is True
            and row.get("status") == "ACTIVE"
        )
        return InstrumentSnapshot(
            symbol=str(row["symbol"]),
            name=str(row["name"]),
            market=str(row["market"]),
            currency=str(row["currency"]),
            security_type=(
                "common_stock" if is_active_common_stock else _optional(row, "securityType")
            ),
            listing_status="listed" if is_active_common_stock else _optional(row, "status"),
            status=_optional(row, "status"),
            is_common_share=_optional_bool(row, "isCommonShare"),
            list_date=_optional_date(row, "listDate"),
            delist_date=_optional_date(row, "delistDate"),
            korean_market_detail=None if detail is None else str(detail),
            exchange=_optional(row, "exchange"),
            country="KR",
            source=PROVIDER,
            as_of=as_of,
        )

    @staticmethod
    def _rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
        value = payload.get(key)
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            TossMarketDataProvider._malformed()
        return value

    @staticmethod
    def _malformed(exc: Exception | None = None) -> Never:
        error = ProviderMalformedResponseError("Malformed provider response", provider=PROVIDER)
        if exc:
            raise error from exc
        raise error


def _error_details(
    response: httpx.Response, *, authentication: bool = False
) -> tuple[str | None, str | None, str | None]:
    try:
        if authentication:
            oauth = OAuthErrorEnvelope.model_validate(response.json())
            return oauth.error, None, oauth.error_description
        envelope = TossErrorEnvelope.model_validate(response.json()).error
        return envelope.code, envelope.requestId, envelope.message
    except (ValueError, ValidationError):
        return None, None, None


def _raise_response_error(response: httpx.Response, *, authentication: bool = False) -> None:
    code, body_request_id, message = _error_details(response, authentication=authentication)
    request_id = body_request_id or response.headers.get("X-Request-ID")
    common: dict[str, Any] = {
        "provider": PROVIDER,
        "provider_code": code,
        "request_id": request_id,
        "provider_message": message,
    }
    if response.status_code == 400:
        raise ProviderValidationError("Provider rejected the request", **common)
    if response.status_code == 401:
        raise ProviderAuthenticationError("Provider authentication failed", **common)
    if response.status_code == 403:
        raise ProviderForbiddenError("Provider access is forbidden", **common)
    if response.status_code == 404:
        raise ProviderNotFoundError("Provider resource not found", **common)
    if response.status_code == 429:
        wait = _retry_after(
            response.headers.get("Retry-After"), response.headers.get("X-RateLimit-Reset")
        )
        raise ProviderRateLimitError(
            "Provider rate limit exceeded", retryable=True, retry_after=wait, **common
        )
    if response.status_code >= 500:
        raise ProviderUnavailableError("Provider is unavailable", retryable=True, **common)
    raise (
        ProviderAuthenticationError("Token issuance failed", **common)
        if authentication
        else ProviderValidationError("Provider rejected the request", **common)
    )


def _retry_after(value: str | None, reset: str | None = None) -> float:
    candidate = value if value is not None else reset
    if candidate is None:
        return 0.1
    try:
        number = float(candidate)
        if value is None:
            number -= datetime.now(UTC).timestamp()
        return max(0.0, min(number, 30.0))
    except (ValueError, OverflowError):
        try:
            parsed = email.utils.parsedate_to_datetime(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return max(0.0, min((parsed - datetime.now(UTC)).total_seconds(), 30.0))
        except (TypeError, ValueError, OverflowError):
            return 0.1


def _decimal(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("invalid decimal")
    return result


def _integer(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("invalid integer")
    result = int(str(value))
    if result < 0 or Decimal(str(value)) != result:
        raise ValueError("invalid integer")
    return result


def _parse_datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed


def _optional(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    return None if value is None else str(value)


def _optional_bool(row: dict[str, Any], key: str) -> bool | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError("expected boolean")
    return value


def _optional_date(row: dict[str, Any], key: str) -> date | None:
    value = row.get(key)
    return None if value in (None, "") else date.fromisoformat(str(value))


def _warning_active(row: dict[str, Any]) -> bool:
    end = _optional_date(row, "endDate")
    return end is None or end >= date.today()
