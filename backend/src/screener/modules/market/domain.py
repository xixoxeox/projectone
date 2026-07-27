from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field, model_validator


class ProviderState(StrEnum):
    UNCONFIGURED = "unconfigured"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ProviderStatus(BaseModel):
    provider: str
    configured: bool = True
    state: ProviderState
    as_of: datetime
    api_base_host: str | None = None
    api_version: str | None = None
    message: str | None = None
    last_successful_request_at: datetime | None = None


class InstrumentSnapshot(BaseModel):
    symbol: str
    name: str
    market: str
    country: str | None = None
    currency: str
    security_type: str | None = None
    listing_status: str | None = None
    exchange: str | None = None
    source: str
    as_of: datetime


class DailyBar(BaseModel):
    symbol: str
    trading_date: date
    open: Decimal = Field(ge=0)
    high: Decimal = Field(ge=0)
    low: Decimal = Field(ge=0)
    close: Decimal = Field(ge=0)
    volume: int = Field(ge=0)
    source: str
    as_of: datetime

    @model_validator(mode="after")
    def valid_ohlc(self) -> "DailyBar":
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high is inconsistent with OHLC values")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low is inconsistent with OHLC values")
        return self


class QuoteSnapshot(BaseModel):
    symbol: str
    price: Decimal = Field(ge=0)
    currency: str
    source: str
    as_of: datetime
    delayed: bool | None = None


class StockWarning(BaseModel):
    symbol: str
    warning_type: str
    active: bool
    description: str | None = None
    source: str
    as_of: datetime


class ProviderError(Exception):
    """A safe, provider-neutral failure with structured upstream diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        retryable: bool = False,
        provider_code: str | None = None,
        request_id: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable
        self.provider_code = provider_code
        self.request_id = request_id
        self.retry_after = retry_after


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderForbiddenError(ProviderError):
    pass


class ProviderNotFoundError(ProviderError):
    pass


class ProviderValidationError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class ProviderMalformedResponseError(ProviderError):
    pass


class MarketDataProvider(Protocol):
    async def status(self) -> ProviderStatus: ...
    async def instrument(self, symbol: str) -> InstrumentSnapshot: ...
    async def daily_bars(self, symbol: str, start: date, end: date) -> list[DailyBar]: ...
    async def prices(self, symbols: list[str]) -> list[QuoteSnapshot]: ...
    async def warnings(self, symbol: str) -> list[StockWarning]: ...
