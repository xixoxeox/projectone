"""Event-based notification framework."""

from screener.modules.notifications.events import (
    NotificationEvent,
    PipelineFailedEvent,
    PipelineManualRunEvent,
    PipelineRecoveredEvent,
    PipelineSucceededEvent,
    TriggerType,
)
from screener.modules.notifications.pipeline import NotificationPublishingPipeline, PipelineResult
from screener.modules.notifications.providers import (
    NotificationProvider,
    NullNotificationProvider,
    SlackNotificationProvider,
)
from screener.modules.notifications.service import NotificationService, build_notification_service

__all__ = [
    "NotificationEvent",
    "NotificationProvider",
    "NotificationPublishingPipeline",
    "NotificationService",
    "NullNotificationProvider",
    "PipelineFailedEvent",
    "PipelineManualRunEvent",
    "PipelineResult",
    "PipelineRecoveredEvent",
    "PipelineSucceededEvent",
    "SlackNotificationProvider",
    "TriggerType",
    "build_notification_service",
]
