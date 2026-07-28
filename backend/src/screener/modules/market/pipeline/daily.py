"""Complete daily watchlist application pipeline."""

from datetime import date
from time import monotonic
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from screener.modules.market.indicators import IndicatorService
from screener.modules.market.infrastructure.repositories import DailyBarRepository, StockRepository
from screener.modules.market.pipeline.models import (
    ExecutionStatus,
    PipelineResult,
    PipelineStage,
    TriggerType,
)
from screener.modules.market.ranking import CandidateRanker
from screener.modules.market.scanning import CandidateScanner, ScanInput
from screener.modules.market.watchlist import WatchlistRepository


class DailyWatchlistPipeline:
    """Synchronize, screen, rank, and persist one complete daily watchlist."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        indicators: IndicatorService,
        scanner: CandidateScanner,
        ranker: CandidateRanker,
    ) -> None:
        self._sessions = sessions
        self._indicators = indicators
        self._scanner = scanner
        self._ranker = ranker

    async def run(self, trigger_type: TriggerType) -> PipelineResult:
        """Execute every stage and describe failure without notification concerns."""
        execution_id = uuid4()
        trading_date = date.today()
        started = monotonic()
        stage = PipelineStage.SCANNING
        try:
            async with self._sessions() as session:
                stocks = await StockRepository(session).active()
                histories = await DailyBarRepository(session).history(
                    [stock.symbol for stock in stocks]
                )
                inputs = [
                    ScanInput(symbol, bars, self._indicators.calculate(bars))
                    for symbol, bars in histories.items()
                ]
                candidates = self._scanner.scan(inputs)
                stage = PipelineStage.RANKING
                ranked = self._ranker.rank(candidates)
                stage = PipelineStage.PERSISTENCE
                await WatchlistRepository(session).save(trading_date, ranked)
                await session.commit()
            return PipelineResult(
                trading_date,
                execution_id,
                trigger_type,
                ExecutionStatus.SUCCEEDED,
                candidate_count=len(candidates),
                persisted_count=len(ranked),
                duration_seconds=monotonic() - started,
            )
        except Exception as exc:
            return PipelineResult(
                trading_date,
                execution_id,
                trigger_type,
                ExecutionStatus.FAILED,
                duration_seconds=monotonic() - started,
                stage=stage,
                error_code=type(exc).__name__,
            )


__all__ = ["DailyWatchlistPipeline"]
