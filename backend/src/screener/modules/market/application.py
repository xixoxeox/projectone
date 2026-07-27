from datetime import UTC, date, datetime

from pydantic import BaseModel

from screener.modules.market.domain import DailyBar, MarketDataProvider, ProviderStatus


class BarsResult(BaseModel):
    symbol: str
    bars: list[DailyBar]
    source: str
    as_of: datetime
    timezone: str = "Asia/Seoul"
    stale: bool


class MarketDataService:
    MAX_RANGE_DAYS = 366

    def __init__(self, provider: MarketDataProvider) -> None:
        self.provider = provider

    async def status(self) -> ProviderStatus:
        return await self.provider.status()

    async def daily_bars(self, symbol: str, start: date, end: date) -> BarsResult:
        if start > end:
            raise ValueError("start_date must not be after end_date")
        if (end - start).days > self.MAX_RANGE_DAYS:
            raise ValueError("date range must not exceed 366 days")
        symbol = symbol.strip().upper()
        if not symbol or len(symbol) > 32 or not symbol.replace("-", "").isalnum():
            raise ValueError("invalid instrument symbol")
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
