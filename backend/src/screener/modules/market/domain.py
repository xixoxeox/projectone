from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field


class ProviderState(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ProviderStatus(BaseModel):
    provider: str
    state: ProviderState
    as_of: datetime
    message: str | None = None


class InstrumentSnapshot(BaseModel):
    symbol: str
    name: str
    market: str
    currency: str
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


class QuoteSnapshot(BaseModel):
    symbol: str
    price: Decimal = Field(ge=0)
    source: str
    as_of: datetime
    delayed: bool


class ProviderError(Exception):
    """A safe, provider-neutral failure."""

    def __init__(self, message: str, *, provider: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class ProviderAuthenticationError(ProviderError):
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
