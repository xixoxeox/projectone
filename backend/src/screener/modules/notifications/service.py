"""Failure-isolating notification application service."""

import logging
from time import monotonic

import httpx

from screener.config import Settings
from screener.modules.notifications.events import NotificationEvent
from screener.modules.notifications.providers import (
    NotificationProvider,
    NullNotificationProvider,
    SlackNotificationProvider,
)

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, provider: NotificationProvider) -> None:
        self.provider = provider

    async def publish(self, event: NotificationEvent) -> None:
        """Deliver an event without allowing transport failures into business logic."""
        started = monotonic()
        try:
            await self.provider.send(event)
        except Exception:
            logger.exception(
                "notification_delivery_failed",
                extra={
                    "provider": self.provider.name,
                    "event_type": event.event_type,
                    "delivery_status": "failed",
                    "attempt": None,
                    "duration": monotonic() - started,
                },
            )
        else:
            logger.info(
                "notification_delivery_completed",
                extra={
                    "provider": self.provider.name,
                    "event_type": event.event_type,
                    "delivery_status": "delivered",
                    "attempt": None,
                    "duration": monotonic() - started,
                },
            )


def build_notification_service(
    settings: Settings, client: httpx.AsyncClient
) -> NotificationService:
    """Select a provider from validated settings at the composition root."""
    if not settings.notification_enabled:
        return NotificationService(NullNotificationProvider())
    if settings.notification_provider == "slack":
        assert settings.slack_webhook_url is not None
        return NotificationService(
            SlackNotificationProvider(
                client,
                settings.slack_webhook_url.get_secret_value(),
                timeout_seconds=settings.slack_timeout_seconds,
                max_attempts=settings.slack_max_retries,
            )
        )
    raise ValueError(f"Unsupported notification provider: {settings.notification_provider}")
