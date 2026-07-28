"""Event-based notification framework."""

from screener.modules.market.pipeline.models import (
    ExecutionStatus,
    PipelineResult,
    PipelineStage,
    TriggerType,
)
from screener.modules.notifications.events import (
    NotificationEvent,
    PipelineFailedEvent,
    PipelineManualRunEvent,
    PipelineRecoveredEvent,
    PipelineSucceededEvent,
)
from screener.modules.notifications.pipeline import NotificationPublishingPipeline
from screener.modules.notifications.providers import (
    NotificationProvider,
    NullNotificationProvider,
    SlackNotificationProvider,
)
from screener.modules.notifications.service import NotificationService, build_notification_service

__all__ = [
    "ExecutionStatus",
    "NotificationEvent",
    "NotificationProvider",
    "NotificationPublishingPipeline",
    "NotificationService",
    "NullNotificationProvider",
    "PipelineFailedEvent",
    "PipelineManualRunEvent",
    "PipelineResult",
    "PipelineStage",
    "PipelineRecoveredEvent",
    "PipelineSucceededEvent",
    "SlackNotificationProvider",
    "TriggerType",
    "build_notification_service",
]
