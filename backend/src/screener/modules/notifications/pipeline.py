import logging
from datetime import date
from typing import Protocol

from screener.modules.market.pipeline.models import ExecutionStatus, PipelineResult, TriggerType

from .events import NotificationEvent, NotificationEventType
from .service import NotificationService

logger = logging.getLogger(__name__)


class PipelineRunner(Protocol):
    async def run(
        self,
        trading_date: date | None = None,
        trigger: TriggerType = TriggerType.MANUAL,
        *,
        force_reanalysis: bool = False,
    ) -> PipelineResult: ...


class NotificationPublishingPipeline:
    """Decorate the canonical pipeline; notification failure never changes its result."""

    def __init__(self, pipeline: PipelineRunner, notifications: NotificationService) -> None:
        self.pipeline = pipeline
        self.notifications = notifications

    async def run(
        self,
        trading_date: date | None = None,
        trigger: TriggerType = TriggerType.MANUAL,
        *,
        force_reanalysis: bool = False,
    ) -> PipelineResult:
        result = await self.pipeline.run(trading_date, trigger, force_reanalysis=force_reanalysis)
        event_type = None
        if result.status == ExecutionStatus.SUCCEEDED:
            event_type = NotificationEventType.WATCHLIST_PUBLISHED
        elif result.status == ExecutionStatus.FAILED:
            event_type = NotificationEventType.WATCHLIST_FAILED
        if event_type is not None:
            try:
                await self.notifications.publish(
                    NotificationEvent(
                        type=event_type,
                        trading_date=result.trading_date,
                        execution_id=str(result.execution_id) if result.execution_id else None,
                        candidate_count=result.persisted_count,
                        error_code=result.error_code,
                    )
                )
            except Exception:
                logger.exception("notification_publication_failed event=%s", event_type)
        return result
