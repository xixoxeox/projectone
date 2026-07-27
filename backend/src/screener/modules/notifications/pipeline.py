"""Application-boundary adapter from pipeline outcomes to notification events."""

from collections.abc import Awaitable, Callable

from screener.modules.market.pipeline.models import PipelineResult, PipelineStage, TriggerType
from screener.modules.notifications.events import (
    NotificationEvent,
    PipelineFailedEvent,
    PipelineRecoveredEvent,
    PipelineSucceededEvent,
)
from screener.modules.notifications.service import NotificationService


class NotificationPublishingPipeline:
    """Decorate a pipeline at the application boundary; never alters its result."""

    def __init__(
        self,
        run_pipeline: Callable[[], Awaitable[PipelineResult]],
        notifications: NotificationService,
    ) -> None:
        self._run_pipeline = run_pipeline
        self._notifications = notifications

    async def run(self) -> PipelineResult:
        result = await self._run_pipeline()
        if result.recovered_execution_id is not None:
            await self._notifications.publish(
                PipelineRecoveredEvent(
                    trading_date=result.trading_date,
                    execution_id=result.execution_id,
                    trigger_type=TriggerType.RECOVERY,
                    recovered_execution_id=result.recovered_execution_id,
                )
            )
        if result.succeeded:
            event: NotificationEvent = PipelineSucceededEvent(
                trading_date=result.trading_date,
                execution_id=result.execution_id,
                trigger_type=result.trigger_type,
                candidate_count=result.candidate_count,
                persisted_count=result.persisted_count,
                duration_seconds=result.duration_seconds,
            )
        else:
            event = PipelineFailedEvent(
                trading_date=result.trading_date,
                execution_id=result.execution_id,
                trigger_type=result.trigger_type,
                stage=result.stage or PipelineStage.UNKNOWN,
                error_code=result.error_code or "pipeline_failed",
                duration_seconds=result.duration_seconds,
            )
        await self._notifications.publish(event)
        return result


__all__ = ["NotificationPublishingPipeline"]
