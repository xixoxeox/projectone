"""SQLAlchemy persistence and retrieval for ranked watchlist candidates."""

import builtins
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from pydantic import TypeAdapter
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.market.infrastructure.models import WatchlistPipelineExecution
from screener.modules.market.ranking.models import RankedCandidate
from screener.modules.market.screening.models import ScreeningResult
from screener.modules.market.watchlist.models import WatchlistEntry, WatchlistEntryRecord

_COMPONENT_SCORES = TypeAdapter(dict[str, Decimal])
_WARNINGS = TypeAdapter(list[str])


class WatchlistRepository:
    """Store watchlists by date.

    Saving a date uses replace semantics: its previous entries are atomically replaced by
    the supplied candidates. Other trading dates are never changed.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, trading_date: date, candidates: Sequence[RankedCandidate]) -> None:
        """Validate and atomically replace all entries for ``trading_date``."""
        self._validate(trading_date, candidates)
        records = [self._record(trading_date, candidate) for candidate in candidates]

        # A savepoint keeps deletion and insertion indivisible even when the caller owns the
        # surrounding transaction (as the application's session dependency does).
        async with self._session.begin_nested():
            await self._session.execute(
                delete(WatchlistEntryRecord).where(
                    WatchlistEntryRecord.trading_date == trading_date
                )
            )
            self._session.add_all(records)
            await self._session.flush()

    async def list(self, trading_date: date) -> builtins.list[WatchlistEntry]:
        """Return one day's entries ordered by ascending rank."""
        records = await self._session.scalars(
            select(WatchlistEntryRecord)
            .where(WatchlistEntryRecord.trading_date == trading_date)
            .order_by(WatchlistEntryRecord.rank.asc())
        )
        return [self._entry(record) for record in records]

    async def latest(self) -> builtins.list[WatchlistEntry]:
        """Return the newest stored trading date, or an empty list."""
        execution_date = await self._session.scalar(
            select(func.max(WatchlistPipelineExecution.trading_date)).where(
                WatchlistPipelineExecution.status == "succeeded"
            )
        )
        if execution_date is not None:
            return await self.list(execution_date)
        latest_date = await self._session.scalar(
            select(func.max(WatchlistEntryRecord.trading_date))
        )
        if latest_date is None:
            return []
        return await self.list(latest_date)

    async def history(self) -> builtins.list[date]:
        """Return stored trading dates ordered from newest to oldest."""
        entry_dates = await self._session.scalars(
            select(WatchlistEntryRecord.trading_date)
            .distinct()
            .order_by(WatchlistEntryRecord.trading_date.desc())
        )
        execution_dates = await self._session.scalars(
            select(WatchlistPipelineExecution.trading_date)
            .where(WatchlistPipelineExecution.status == "succeeded")
            .distinct()
        )
        return sorted(set(entry_dates) | set(execution_dates), reverse=True)

    async def has_successful_execution(self, trading_date: date) -> bool:
        return (
            await self._session.scalar(
                select(WatchlistPipelineExecution.id)
                .where(
                    WatchlistPipelineExecution.trading_date == trading_date,
                    WatchlistPipelineExecution.status == "succeeded",
                )
                .limit(1)
            )
            is not None
        )

    async def get(self, trading_date: date, symbol: str) -> WatchlistEntry | None:
        """Return one entry for a date and symbol, if it exists."""
        record = await self._session.scalar(
            select(WatchlistEntryRecord).where(
                WatchlistEntryRecord.trading_date == trading_date,
                WatchlistEntryRecord.symbol == symbol,
            )
        )
        return None if record is None else self._entry(record)

    async def exists(self, trading_date: date) -> bool:
        """Return whether at least one entry exists for ``trading_date``."""
        entry_id = await self._session.scalar(
            select(WatchlistEntryRecord.id)
            .where(WatchlistEntryRecord.trading_date == trading_date)
            .limit(1)
        )
        return entry_id is not None

    async def delete(self, trading_date: date) -> None:
        """Delete only entries belonging to ``trading_date``."""
        await self._session.execute(
            delete(WatchlistEntryRecord).where(WatchlistEntryRecord.trading_date == trading_date)
        )

    @staticmethod
    def _validate(trading_date: date, candidates: Sequence[RankedCandidate]) -> None:
        if not isinstance(trading_date, date):
            raise ValueError("trading_date must not be empty")

        symbols: set[str] = set()
        ranks: set[int] = set()
        for candidate in candidates:
            if not candidate.symbol.strip():
                raise ValueError("candidate symbol must not be blank")
            if candidate.symbol in symbols:
                raise ValueError(f"duplicate symbol: {candidate.symbol}")
            if candidate.rank in ranks:
                raise ValueError(f"duplicate rank: {candidate.rank}")
            symbols.add(candidate.symbol)
            ranks.add(candidate.rank)

    @staticmethod
    def _record(trading_date: date, candidate: RankedCandidate) -> WatchlistEntryRecord:
        return WatchlistEntryRecord(
            trading_date=trading_date,
            symbol=candidate.symbol,
            rank=candidate.rank,
            total_score=str(candidate.total_score),
            component_scores=_COMPONENT_SCORES.dump_json(candidate.component_scores).decode(),
            warnings=_WARNINGS.dump_json(candidate.warnings).decode(),
            snapshot=candidate.source_result.model_dump_json(),
        )

    @staticmethod
    def _entry(record: WatchlistEntryRecord) -> WatchlistEntry:
        return WatchlistEntry(
            id=record.id,
            trading_date=record.trading_date,
            symbol=record.symbol,
            rank=record.rank,
            total_score=Decimal(record.total_score),
            component_scores=_COMPONENT_SCORES.validate_json(record.component_scores),
            warnings=_WARNINGS.validate_json(record.warnings),
            snapshot=ScreeningResult.model_validate_json(record.snapshot),
        )


__all__ = ["WatchlistRepository"]
