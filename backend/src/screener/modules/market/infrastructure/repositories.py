from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable

from screener.modules.market.domain import DailyBar, InstrumentSnapshot
from screener.modules.market.infrastructure.models import (
    DailyBarRecord,
    Stock,
    SyncJob,
    SyncJobRun,
)


@dataclass(frozen=True)
class UpsertResult:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0


def _values_equal(left: object, right: object) -> bool:
    if isinstance(left, datetime) and isinstance(right, datetime):
        left_utc = left.replace(tzinfo=UTC) if left.tzinfo is None else left.astimezone(UTC)
        right_utc = right.replace(tzinfo=UTC) if right.tzinfo is None else right.astimezone(UTC)
        return left_utc == right_utc
    return left == right


def _stock_upsert_statement(rows: list[dict[str, object]], *, sqlite: bool) -> Executable:
    if sqlite:
        sqlite_statement = sqlite_insert(Stock).values(rows)
        sqlite_excluded = sqlite_statement.excluded
        return sqlite_statement.on_conflict_do_update(
            index_elements=[Stock.symbol],
            set_={
                "name": sqlite_excluded.name,
                "market": sqlite_excluded.market,
                "exchange": sqlite_excluded.exchange,
                "currency": sqlite_excluded.currency,
                "country": sqlite_excluded.country,
                "security_type": sqlite_excluded.security_type,
                "listing_status": sqlite_excluded.listing_status,
                "is_active": sqlite_excluded.is_active,
                "updated_at": func.now(),
            },
        )
    postgres_statement = pg_insert(Stock).values(rows)
    postgres_excluded = postgres_statement.excluded
    return postgres_statement.on_conflict_do_update(
        index_elements=[Stock.symbol],
        set_={
            "name": postgres_excluded.name,
            "market": postgres_excluded.market,
            "exchange": postgres_excluded.exchange,
            "currency": postgres_excluded.currency,
            "country": postgres_excluded.country,
            "security_type": postgres_excluded.security_type,
            "listing_status": postgres_excluded.listing_status,
            "is_active": postgres_excluded.is_active,
            "updated_at": func.now(),
        },
    )


def _daily_bar_upsert_statement(rows: list[dict[str, object]], *, sqlite: bool) -> Executable:
    if sqlite:
        sqlite_statement = sqlite_insert(DailyBarRecord).values(rows)
        sqlite_excluded = sqlite_statement.excluded
        return sqlite_statement.on_conflict_do_update(
            index_elements=[DailyBarRecord.symbol, DailyBarRecord.trading_date],
            set_={
                "open": sqlite_excluded.open,
                "high": sqlite_excluded.high,
                "low": sqlite_excluded.low,
                "close": sqlite_excluded.close,
                "volume": sqlite_excluded.volume,
                "source": sqlite_excluded.source,
                "provider_timestamp": sqlite_excluded.provider_timestamp,
                "updated_at": func.now(),
            },
        )
    postgres_statement = pg_insert(DailyBarRecord).values(rows)
    postgres_excluded = postgres_statement.excluded
    return postgres_statement.on_conflict_do_update(
        constraint="uq_daily_bars_symbol_date",
        set_={
            "open": postgres_excluded.open,
            "high": postgres_excluded.high,
            "low": postgres_excluded.low,
            "close": postgres_excluded.close,
            "volume": postgres_excluded.volume,
            "source": postgres_excluded.source,
            "provider_timestamp": postgres_excluded.provider_timestamp,
            "updated_at": func.now(),
        },
    )


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
        rows: list[dict[str, object]] = []
        for x in items:
            row: dict[str, object] = {
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
            is_sqlite = self.session.bind is not None and self.session.bind.dialect.name == "sqlite"
            statement = _stock_upsert_statement(rows, sqlite=is_sqlite)
            await self.session.execute(statement)
        return UpsertResult(inserted, updated, skipped)


class DailyBarRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def latest_dates(self, symbols: list[str]) -> dict[str, date]:
        if not symbols:
            return {}
        result = await self.session.execute(
            select(DailyBarRecord.symbol, func.max(DailyBarRecord.trading_date))
            .where(DailyBarRecord.symbol.in_(symbols))
            .group_by(DailyBarRecord.symbol)
        )
        return {symbol: value for symbol, value in result if value is not None}

    async def history(self, symbols: list[str]) -> dict[str, list[DailyBar]]:
        """Return all persisted bars for each symbol in chronological order."""
        if not symbols:
            return {}
        records = (
            await self.session.scalars(
                select(DailyBarRecord)
                .where(DailyBarRecord.symbol.in_(symbols))
                .order_by(DailyBarRecord.symbol, DailyBarRecord.trading_date)
            )
        ).all()
        histories: dict[str, list[DailyBar]] = {symbol: [] for symbol in symbols}
        for record in records:
            histories[record.symbol].append(
                DailyBar(
                    symbol=record.symbol,
                    trading_date=record.trading_date,
                    open=record.open,
                    high=record.high,
                    low=record.low,
                    close=record.close,
                    volume=record.volume,
                    source=record.source,
                    as_of=record.provider_timestamp or record.updated_at,
                )
            )
        return histories

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
        rows: list[dict[str, object]] = []
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
                not _values_equal(getattr(old, k), v)
                for k, v in row.items()
                if k not in {"symbol", "trading_date"}
            ):
                updated += 1
            else:
                skipped += 1
                continue
            rows.append(row)
        if rows:
            is_sqlite = self.session.bind is not None and self.session.bind.dialect.name == "sqlite"
            statement = _daily_bar_upsert_statement(rows, sqlite=is_sqlite)
            await self.session.execute(statement)
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
        started_at = (
            run.started_at.replace(tzinfo=UTC) if run.started_at.tzinfo is None else run.started_at
        )
        run.duration_ms = int((now - started_at).total_seconds() * 1000)
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
