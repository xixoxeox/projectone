from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.market.domain import DailyBar, InstrumentSnapshot
from screener.modules.market.infrastructure.models import DailyBarRecord, Stock, SyncJob, SyncJobRun


@dataclass(frozen=True)
class UpsertResult:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0


class StockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def active(self) -> list[Stock]:
        return list(
            (
                await self.session.scalars(
                    select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.symbol)
                )
            ).all()
        )

    async def upsert(self, items: list[InstrumentSnapshot]) -> UpsertResult:
        if not items:
            return UpsertResult()
        symbols = [x.symbol for x in items]
        old = {
            x.symbol: x
            for x in (
                await self.session.scalars(select(Stock).where(Stock.symbol.in_(symbols)))
            ).all()
        }
        inserted = updated = skipped = 0
        rows: list[dict[str, Any]] = []
        for x in items:
            row = {
                "symbol": x.symbol,
                "name": x.name,
                "market": x.market,
                "exchange": x.exchange,
                "currency": x.currency,
                "country": x.country or "KR",
                "security_type": x.security_type,
                "listing_status": x.listing_status,
                "is_active": x.listing_status not in {"delisted", "inactive"},
            }
            current = old.get(x.symbol)
            if current is None:
                inserted += 1
            elif any(getattr(current, k) != v for k, v in row.items() if k != "symbol"):
                updated += 1
            else:
                skipped += 1
                continue
            rows.append(row)
        if rows:
            stmt = pg_insert(Stock).values(rows)
            excluded = stmt.excluded
            await self.session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[Stock.symbol],
                    set_={
                        "name": excluded.name,
                        "market": excluded.market,
                        "exchange": excluded.exchange,
                        "currency": excluded.currency,
                        "country": excluded.country,
                        "security_type": excluded.security_type,
                        "listing_status": excluded.listing_status,
                        "is_active": excluded.is_active,
                        "updated_at": func.now(),
                    },
                )
            )
        return UpsertResult(inserted, updated, skipped)


class DailyBarRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def latest_dates(self, symbols: list[str]) -> dict[str, date]:
        result = await self.session.execute(
            select(DailyBarRecord.symbol, func.max(DailyBarRecord.trading_date))
            .where(DailyBarRecord.symbol.in_(symbols))
            .group_by(DailyBarRecord.symbol)
        )
        return {symbol: value for symbol, value in result if value is not None}

    async def upsert(self, bars: list[DailyBar]) -> UpsertResult:
        keys = [(x.symbol, x.trading_date) for x in bars]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate trading dates in batch")
        if not bars:
            return UpsertResult()
        existing = {
            (x.symbol, x.trading_date): x
            for x in (
                await self.session.scalars(
                    select(DailyBarRecord).where(
                        DailyBarRecord.symbol.in_({b.symbol for b in bars}),
                        DailyBarRecord.trading_date.in_({b.trading_date for b in bars}),
                    )
                )
            ).all()
        }
        rows = []
        inserted = updated = skipped = 0
        for b in bars:
            row = {
                "symbol": b.symbol,
                "trading_date": b.trading_date,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "source": b.source,
                "provider_timestamp": b.as_of,
            }
            old = existing.get((b.symbol, b.trading_date))
            if old is None:
                inserted += 1
            elif any(
                getattr(old, k) != v for k, v in row.items() if k not in {"symbol", "trading_date"}
            ):
                updated += 1
            else:
                skipped += 1
                continue
            rows.append(row)
        if rows:
            stmt = pg_insert(DailyBarRecord).values(rows)
            e = stmt.excluded
            await self.session.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_daily_bars_symbol_date",
                    set_={
                        "open": e.open,
                        "high": e.high,
                        "low": e.low,
                        "close": e.close,
                        "volume": e.volume,
                        "source": e.source,
                        "provider_timestamp": e.provider_timestamp,
                        "updated_at": func.now(),
                    },
                )
            )
        return UpsertResult(inserted, updated, skipped)


class SyncJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start(self, name: str) -> SyncJobRun:
        job = await self.session.get(SyncJob, name)
        if job is None:
            job = SyncJob(name=name)
            self.session.add(job)
            await self.session.flush()
        run = SyncJobRun(job_name=name, started_at=datetime.now(UTC), status="running")
        self.session.add(run)
        await self.session.flush()
        return run

    async def finish(self, run: SyncJobRun, result: UpsertResult, error: str | None = None) -> None:
        now = datetime.now(UTC)
        run.finished_at = now
        run.duration_ms = int((now - run.started_at).total_seconds() * 1000)
        run.status = "failed" if error else "succeeded"
        run.error_message = error
        run.inserted_rows = result.inserted
        run.updated_rows = result.updated
        run.skipped_rows = result.skipped
        job = await self.session.get(SyncJob, run.job_name)
        assert job
        if error:
            job.last_failure_at = now
        else:
            job.last_success_at = now

    async def status(self) -> list[SyncJob]:
        return list((await self.session.scalars(select(SyncJob).order_by(SyncJob.name))).all())

    async def history(self, limit: int = 50) -> list[SyncJobRun]:
        return list(
            (
                await self.session.scalars(
                    select(SyncJobRun).order_by(SyncJobRun.started_at.desc()).limit(limit)
                )
            ).all()
        )
