"""One orchestration path shared by scheduled and administrative invocations."""

import logging
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.service import IndicatorService
from screener.modules.market.infrastructure.models import DailyBarRecord, WatchlistPipelineExecution
from screener.modules.market.pipeline.models import (
    ExecutionStatus,
    PipelineResult,
    PipelineStage,
    TriggerType,
)
from screener.modules.market.pipeline.repository import PipelineExecutionRepository
from screener.modules.market.ranking.ranker import CandidateRanker
from screener.modules.market.scanning.models import ScanInput
from screener.modules.market.scanning.scanner import CandidateScanner
from screener.modules.market.sync import SyncCoordinator
from screener.modules.market.watchlist.repository import WatchlistRepository

logger = logging.getLogger(__name__)


class DailyWatchlistPipeline:
    """Coordinate existing services without owning their market or ranking rules."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        sync: SyncCoordinator,
        indicators: IndicatorService,
        scanner: CandidateScanner,
        ranker: CandidateRanker,
        timezone: str = "Asia/Seoul",
    ) -> None:
        self.sessions, self.sync, self.indicators = sessions, sync, indicators
        self.scanner, self.ranker, self.timezone = scanner, ranker, ZoneInfo(timezone)

    async def run(
        self, trading_date: date | None = None, trigger: TriggerType = TriggerType.MANUAL
    ) -> PipelineResult:
        started = datetime.now(UTC)
        target = trading_date or datetime.now(self.timezone).date()
        if target.weekday() >= 5:
            return PipelineResult(
                trading_date=target,
                status=ExecutionStatus.SKIPPED,
                started_at=started,
                finished_at=datetime.now(UTC),
                stage=PipelineStage.RESOLVING_TRADING_DATE,
                skipped_reason="weekend",
            )
        async with self.sessions() as session:
            run = await PipelineExecutionRepository(session).acquire(target, trigger)
        if run is None:
            return PipelineResult(
                trading_date=target,
                status=ExecutionStatus.SKIPPED,
                started_at=started,
                finished_at=datetime.now(UTC),
                stage=PipelineStage.DUPLICATE_CHECK,
                skipped_reason="already_running_or_completed",
            )

        stage = PipelineStage.MARKET_SYNC
        try:
            await self._stage(run.id, stage)
            await self.sync.all()
            stage = PipelineStage.INDICATOR_CALCULATION
            await self._stage(run.id, stage)
            inputs = await self._inputs(target)
            if not inputs:
                return await self._finish_skipped(run.id, target, started, "no_market_data")
            stage = PipelineStage.SCREENING
            await self._stage(run.id, stage)
            stage = PipelineStage.CANDIDATE_SCANNING
            await self._stage(run.id, stage)
            candidates = self.scanner.scan(inputs)
            stage = PipelineStage.CANDIDATE_RANKING
            await self._stage(run.id, stage)
            ranked = self.ranker.rank(candidates)
            if not ranked:
                return await self._finish_skipped(run.id, target, started, "no_candidates", 0)
            stage = PipelineStage.WATCHLIST_PERSISTENCE
            await self._stage(run.id, stage)
            async with self.sessions() as session:
                await WatchlistRepository(session).save(target, ranked)
                await session.commit()
            async with self.sessions() as session:
                record = await PipelineExecutionRepository(session).finish(
                    run.id,
                    status=ExecutionStatus.SUCCEEDED,
                    stage=PipelineStage.COMPLETED,
                    candidate_count=len(candidates),
                    persisted_count=len(ranked),
                )
            result = self._result(record)
            logger.info(
                "watchlist_pipeline_complete execution_id=%s trading_date=%s status=%s "
                "candidate_count=%d persisted_count=%d duration_ms=%d",
                run.id,
                target,
                result.status,
                len(candidates),
                len(ranked),
                int((datetime.now(UTC) - started).total_seconds() * 1000),
            )
            return result
        except Exception as exc:
            logger.exception(
                "watchlist_pipeline_failed execution_id=%s trading_date=%s stage=%s",
                run.id,
                target,
                stage,
            )
            async with self.sessions() as session:
                record = await PipelineExecutionRepository(session).finish(
                    run.id,
                    status=ExecutionStatus.FAILED,
                    stage=stage,
                    error_code=f"{stage.value}_failed",
                    error_detail=type(exc).__name__[:200],
                )
            return self._result(record)

    async def _stage(self, execution_id: uuid.UUID, stage: PipelineStage) -> None:
        async with self.sessions() as session:
            await PipelineExecutionRepository(session).set_stage(execution_id, stage)

    async def _inputs(self, target: date) -> list[ScanInput]:
        async with self.sessions() as session:
            records = (
                await session.scalars(
                    select(DailyBarRecord)
                    .where(DailyBarRecord.trading_date <= target)
                    .order_by(DailyBarRecord.symbol, DailyBarRecord.trading_date)
                )
            ).all()
        grouped: dict[str, list[DailyBar]] = defaultdict(list)
        for row in records:
            grouped[row.symbol].append(
                DailyBar(
                    symbol=row.symbol,
                    trading_date=row.trading_date,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    close=row.close,
                    volume=row.volume,
                    source=row.source,
                    as_of=row.provider_timestamp or datetime.now(UTC),
                )
            )
        # A date is valid only when at least one provider-confirmed bar exists on that date.
        return [
            ScanInput(symbol=symbol, bars=bars, indicators=self.indicators.calculate(bars))
            for symbol, bars in grouped.items()
            if bars and bars[-1].trading_date == target
        ]

    async def _finish_skipped(
        self,
        execution_id: uuid.UUID,
        target: date,
        started: datetime,
        reason: str,
        count: int | None = None,
    ) -> PipelineResult:
        async with self.sessions() as session:
            record = await PipelineExecutionRepository(session).finish(
                execution_id,
                status=ExecutionStatus.SKIPPED,
                stage=PipelineStage.COMPLETED,
                candidate_count=count,
                persisted_count=0,
                skipped_reason=reason,
            )
        return self._result(record)

    @staticmethod
    def _result(record: WatchlistPipelineExecution) -> PipelineResult:
        return PipelineResult(
            execution_id=record.id,
            trading_date=record.trading_date,
            status=record.status,
            started_at=record.started_at,
            finished_at=record.finished_at,
            stage=record.stage,
            candidate_count=record.candidate_count,
            persisted_count=record.persisted_count,
            skipped_reason=record.skipped_reason,
            error_code=record.error_code,
        )
