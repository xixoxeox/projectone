import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from screener.modules.market.domain import MarketDataProvider
from screener.modules.market.infrastructure.models import SyncJobRun
from screener.modules.market.infrastructure.repositories import (
    DailyBarRepository,
    StockRepository,
    SyncJobRepository,
    UpsertResult,
)

logger = logging.getLogger(__name__)


class SyncAlreadyRunningError(RuntimeError):
    def __init__(self, job_name: str) -> None:
        super().__init__(f"Synchronization job '{job_name}' is already running")
        self.job_name = job_name


class SyncResult(BaseModel):
    job_name: str
    status: str
    inserted_rows: int
    updated_rows: int
    skipped_rows: int
    duration_ms: int


class _Runner:
    name: str

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], provider: MarketDataProvider
    ) -> None:
        self.sessions, self.provider = sessions, provider
        self._run_lock = asyncio.Lock()

    async def run(self) -> SyncResult:
        if self._run_lock.locked():
            raise SyncAlreadyRunningError(self.name)
        await self._run_lock.acquire()
        try:
            return await self._run_locked()
        finally:
            self._run_lock.release()

    async def _run_locked(self) -> SyncResult:
        started = datetime.now(UTC)
        async with self.sessions() as session:
            jobs = SyncJobRepository(session)
            run = await jobs.start(self.name)
            await session.commit()
            try:
                result = await self._sync(session)
                await session.commit()
                await jobs.finish(run, result)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                stored_run = await session.get(SyncJobRun, run.id)
                if stored_run is None:
                    raise
                await jobs.finish(stored_run, UpsertResult(), str(exc)[:2000])
                await session.commit()
                logger.exception(
                    "sync_failed job_name=%s duration_ms=%d",
                    self.name,
                    int((datetime.now(UTC) - started).total_seconds() * 1000),
                )
                raise
        duration = int((datetime.now(UTC) - started).total_seconds() * 1000)
        logger.info(
            "sync_complete job_name=%s inserted=%d updated=%d skipped=%d duration_ms=%d",
            self.name,
            result.inserted,
            result.updated,
            result.skipped,
            duration,
        )
        return SyncResult(
            job_name=self.name,
            status="succeeded",
            duration_ms=duration,
            inserted_rows=result.inserted,
            updated_rows=result.updated,
            skipped_rows=result.skipped,
        )

    async def _sync(self, session: AsyncSession) -> UpsertResult:
        raise NotImplementedError


class StockSyncService(_Runner):
    name = "stock_master"

    async def _sync(self, session: AsyncSession) -> UpsertResult:
        snapshots = await self.provider.stock_master("KOSPI")
        if len({x.symbol for x in snapshots}) != len(snapshots):
            raise ValueError("duplicate symbols in stock master")
        return await StockRepository(session).upsert(snapshots)


class DailyBarSyncService(_Runner):
    name = "daily_bars"

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        provider: MarketDataProvider,
        history_years: int = 3,
        batch_size: int = 500,
    ) -> None:
        super().__init__(sessions, provider)
        self.history_years = history_years
        self.batch_size = batch_size

    async def _sync(self, session: AsyncSession) -> UpsertResult:
        stocks = await StockRepository(session).active()
        symbols = [x.symbol for x in stocks]
        latest = await DailyBarRepository(session).latest_dates(symbols)
        end = date.today()
        total = UpsertResult()
        for offset in range(0, len(symbols), self.batch_size):
            for symbol in symbols[offset : offset + self.batch_size]:
                start = (
                    latest[symbol] + timedelta(days=1)
                    if symbol in latest
                    else end - timedelta(days=365 * self.history_years)
                )
                if start > end:
                    continue
                bars = await self.provider.daily_bars(symbol, start, end)
                if any(x.trading_date > end for x in bars):
                    raise ValueError("future trading date")
                value = await DailyBarRepository(session).upsert(bars)
                total = UpsertResult(
                    total.inserted + value.inserted,
                    total.updated + value.updated,
                    total.skipped + value.skipped,
                )
            await session.commit()
        return total


class SyncCoordinator:
    def __init__(self, stocks: StockSyncService, bars: DailyBarSyncService) -> None:
        self.stocks, self.bars = stocks, bars

    async def all(self) -> list[SyncResult]:
        return [await self.stocks.run(), await self.bars.run()]
