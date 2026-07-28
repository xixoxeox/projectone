from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.backtest.domain import BacktestRun
from screener.modules.market.watchlist.models import WatchlistEntryRecord


class BacktestSignalType(StrEnum):
    ENTER_LONG = "enter_long"


@dataclass(frozen=True, slots=True)
class BacktestSignal:
    symbol: str
    signal_date: date
    type: BacktestSignalType = BacktestSignalType.ENTER_LONG


class BacktestStrategy(Protocol):
    name: str
    version: str

    async def generate_signals(self, run: BacktestRun) -> list[BacktestSignal]: ...


class WatchlistEntryStrategy:
    name = "watchlist_entry"
    version = "1"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def generate_signals(self, run: BacktestRun) -> list[BacktestSignal]:
        rows = await self._session.execute(
            select(WatchlistEntryRecord.symbol, WatchlistEntryRecord.trading_date)
            .where(
                WatchlistEntryRecord.trading_date >= run.start_date,
                WatchlistEntryRecord.trading_date <= run.end_date,
            )
            .order_by(WatchlistEntryRecord.trading_date, WatchlistEntryRecord.symbol)
        )
        return [BacktestSignal(symbol, trading_date) for symbol, trading_date in rows]
