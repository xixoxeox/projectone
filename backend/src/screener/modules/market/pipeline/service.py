"""Canonical, durable daily watchlist pipeline."""

from datetime import UTC, date, datetime, timedelta
from time import monotonic
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from screener.modules.market.indicators import IndicatorService
from screener.modules.market.infrastructure.models import WatchlistPipelineExecution
from screener.modules.market.infrastructure.repositories import (
    DailyBarRepository,
    StockRepository,
)
from screener.modules.market.pipeline.models import (
    ExecutionStatus,
    PipelineResult,
    PipelineStage,
    TriggerType,
)
from screener.modules.market.pipeline.repository import PipelineExecutionRepository
from screener.modules.market.ranking import CandidateRanker
from screener.modules.market.scanning import CandidateScanner, ScanInput
from screener.modules.market.watchlist import WatchlistRepository


class DailyWatchlistPipeline:
    """Own pipeline execution, idempotency, recovery, and durable history."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        indicators: IndicatorService,
        scanner: CandidateScanner,
        ranker: CandidateRanker,
        stale_after: timedelta = timedelta(hours=1),
    ) -> None:
        self._sessions = sessions
        self._indicators = indicators
        self._scanner = scanner
        self._ranker = ranker
        self._stale_after = stale_after

    async def run(self, trigger_type: TriggerType) -> PipelineResult:
        trading_date = date.today()
        execution_id = owner_id = uuid4()
        started = monotonic()
        stage = PipelineStage.SCANNING
        recovered_id = None
        async with self._sessions() as session:
            repository = PipelineExecutionRepository(session)
            if not await repository.acquire_lock():
                return PipelineResult(
                    trading_date, execution_id, trigger_type, ExecutionStatus.ALREADY_RUNNING
                )
            previous = await repository.successful(trading_date)
            if previous is not None:
                return PipelineResult(
                    trading_date,
                    previous.id,
                    trigger_type,
                    ExecutionStatus.ALREADY_SUCCEEDED,
                    candidate_count=previous.candidate_count,
                    persisted_count=previous.persisted_count,
                )
            recovered = await repository.recover_stale(trading_date, self._stale_after)
            if recovered is not None:
                recovered_id = recovered.id
            now = datetime.now(UTC)
            execution = WatchlistPipelineExecution(
                id=execution_id,
                trading_date=trading_date,
                trigger_type=trigger_type.value,
                status=ExecutionStatus.RUNNING.value,
                owner_id=owner_id,
                started_at=now,
                heartbeat_at=now,
                recovered_execution_id=recovered_id,
            )
            session.add(execution)
            await session.flush()
            try:
                stocks = await StockRepository(session).active()
                histories = await DailyBarRepository(session).history([x.symbol for x in stocks])
                inputs = [
                    ScanInput(symbol, bars, self._indicators.calculate(bars))
                    for symbol, bars in histories.items()
                ]
                candidates = self._scanner.scan(inputs)
                stage = PipelineStage.RANKING
                ranked = self._ranker.rank(candidates)
                stage = PipelineStage.PERSISTENCE
                await WatchlistRepository(session).save(trading_date, ranked)
                execution.status = ExecutionStatus.SUCCEEDED.value
                execution.candidate_count = len(candidates)
                execution.persisted_count = len(ranked)
                execution.finished_at = datetime.now(UTC)
                await session.commit()
                return PipelineResult(
                    trading_date,
                    execution_id,
                    trigger_type,
                    ExecutionStatus.SUCCEEDED,
                    len(candidates),
                    len(ranked),
                    monotonic() - started,
                    recovered_execution_id=recovered_id,
                )
            except Exception as exc:
                await session.rollback()
                async with self._sessions() as failure_session:
                    failed = await failure_session.get(WatchlistPipelineExecution, execution_id)
                    if failed is None:
                        failure_session.add(
                            WatchlistPipelineExecution(
                                id=execution_id,
                                trading_date=trading_date,
                                trigger_type=trigger_type.value,
                                status=ExecutionStatus.FAILED.value,
                                owner_id=owner_id,
                                started_at=now,
                                heartbeat_at=now,
                            )
                        )
                        await failure_session.flush()
                        failed = await failure_session.get(WatchlistPipelineExecution, execution_id)
                    assert failed is not None
                    failed.status = ExecutionStatus.FAILED.value
                    failed.finished_at = datetime.now(UTC)
                    failed.stage = stage.value
                    failed.error_code = type(exc).__name__
                    await failure_session.commit()
                return PipelineResult(
                    trading_date,
                    execution_id,
                    trigger_type,
                    ExecutionStatus.FAILED,
                    duration_seconds=monotonic() - started,
                    stage=stage,
                    error_code=type(exc).__name__,
                    recovered_execution_id=recovered_id,
                )


__all__ = ["DailyWatchlistPipeline"]
