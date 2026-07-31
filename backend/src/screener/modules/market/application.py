import asyncio
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from screener.modules.market.domain import (
    DailyBar,
    InstrumentSnapshot,
    MarketDataProvider,
    ProviderStatus,
    QuoteSnapshot,
    StockWarning,
)
from screener.modules.market.screening.swing import SwingScreeningConfig
from screener.modules.market.technical_analysis import (
    RealtimeTechnicalAnalysis,
    analyze_realtime,
)


class BarsResult(BaseModel):
    symbol: str
    bars: list[DailyBar]
    source: str
    as_of: datetime
    timezone: str = "Asia/Seoul"
    stale: bool


class PricesResult(BaseModel):
    quotes: list[QuoteSnapshot]
    source: str
    as_of: datetime


class MarketDataService:
    MAX_RANGE_DAYS = 366

    def __init__(
        self,
        provider: MarketDataProvider,
        screening_config: SwingScreeningConfig | None = None,
    ) -> None:
        self.provider = provider
        self.screening_config = screening_config or SwingScreeningConfig()

    async def status(self) -> ProviderStatus:
        return await self.provider.status()

    @staticmethod
    def symbol(value: str) -> str:
        value = value.strip().upper()
        if not value or len(value) > 32 or not value.replace("-", "").isalnum():
            raise ValueError("invalid instrument symbol")
        return value

    async def instrument(self, symbol: str) -> InstrumentSnapshot:
        return await self.provider.instrument(self.symbol(symbol))

    async def daily_bars(self, symbol: str, start: date, end: date) -> BarsResult:
        if start > end:
            raise ValueError("start_date must not be after end_date")
        if (end - start).days > self.MAX_RANGE_DAYS:
            raise ValueError("date range must not exceed 366 days")
        symbol = self.symbol(symbol)
        bars = await self.provider.daily_bars(symbol, start, end)
        now = datetime.now(UTC)
        as_of = max((bar.as_of for bar in bars), default=now)
        return BarsResult(
            symbol=symbol,
            bars=bars,
            source=bars[0].source if bars else "toss",
            as_of=as_of,
            stale=(now - as_of).total_seconds() > 86400,
        )

    async def prices(self, symbols: list[str]) -> PricesResult:
        clean = [self.symbol(symbol) for symbol in symbols]
        quotes = await self.provider.prices(clean)
        now = datetime.now(UTC)
        as_of = max((quote.as_of for quote in quotes), default=now)
        return PricesResult(
            quotes=quotes, source=quotes[0].source if quotes else "toss", as_of=as_of
        )

    async def warnings(self, symbol: str) -> list[StockWarning]:
        return await self.provider.warnings(self.symbol(symbol))

    async def realtime_analysis(self, symbol: str) -> RealtimeTechnicalAnalysis:
        symbol = self.symbol(symbol)
        instrument = await self.provider.instrument(symbol)
        if (
            instrument.market != "KOSPI"
            or instrument.security_type != "common_stock"
            or instrument.listing_status != "listed"
        ):
            raise ValueError("only active KOSPI common stocks are supported")
        today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        prices, daily_bars, minute_bars, warnings = await asyncio.gather(
            self.provider.prices([symbol]),
            self.provider.daily_bars(symbol, today - timedelta(days=240), today),
            self.provider.minute_bars(symbol, 200),
            self.provider.warnings(symbol),
        )
        if len(prices) != 1 or prices[0].symbol != symbol:
            raise ValueError("provider did not return the requested quote")
        return analyze_realtime(
            instrument,
            prices[0],
            daily_bars,
            minute_bars,
            warnings,
            self.screening_config,
        )
