"""Notification provider contracts and Slack transport implementation."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx

from screener.modules.notifications.events import (
    NotificationEvent,
    PipelineFailedEvent,
    PipelineManualRunEvent,
    PipelineRecoveredEvent,
    PipelineSucceededEvent,
)

logger = logging.getLogger(__name__)


class NotificationProvider(Protocol):
    """Transport-agnostic notification delivery contract."""

    name: str

    async def send(self, event: NotificationEvent) -> None: ...


class NullNotificationProvider:
    """Intentionally discard events when notifications are disabled."""

    name = "null"

    async def send(self, event: NotificationEvent) -> None:
        del event


class SlackNotificationProvider:
    """Render structured events and deliver them through an Incoming Webhook."""

    name = "slack"

    def __init__(
        self,
        client: httpx.AsyncClient,
        webhook_url: str,
        *,
        timeout_seconds: float = 10,
        max_attempts: int = 3,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not webhook_url.startswith("https://hooks.slack.com/services/"):
            raise ValueError("webhook_url must be a Slack Incoming Webhook URL")
        if not 1 <= max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        self._client = client
        self._webhook_url = webhook_url
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        self._sleep = sleep

    async def send(self, event: NotificationEvent) -> None:
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.post(
                    self._webhook_url,
                    json={"text": self.format_event(event)},
                    timeout=self._timeout,
                )
                if response.status_code < 400:
                    return
                if response.status_code < 500:
                    response.raise_for_status()
                if attempt == self._max_attempts:
                    response.raise_for_status()
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == self._max_attempts:
                    raise
            if attempt < self._max_attempts:
                delay = float(2 ** (attempt - 1))
                logger.info(
                    "notification_delivery_retry",
                    extra={
                        "provider": self.name,
                        "event_type": event.event_type,
                        "delivery_status": "retrying",
                        "attempt": attempt,
                        "duration": delay,
                    },
                )
                await self._sleep(delay)

    @staticmethod
    def format_event(event: NotificationEvent) -> str:
        if isinstance(event, PipelineSucceededEvent):
            return (
                "✅ *Daily Watchlist Completed*\n\n"
                f"*Trading Date:*\n{event.trading_date.isoformat()}\n\n"
                f"*Trigger:*\n{event.trigger_type.value}\n\n"
                f"*Candidates:*\n{event.candidate_count}\n\n"
                f"*Persisted:*\n{event.persisted_count}\n\n"
                f"*Duration:*\n{event.duration_seconds:.1f} sec\n\n"
                f"*Execution:*\n{event.execution_id}"
            )
        if isinstance(event, PipelineFailedEvent):
            return (
                "❌ *Daily Watchlist Failed*\n\n"
                f"*Stage:*\n{event.stage}\n\n*Error:*\n{event.error_code}\n\n"
                f"*Execution:*\n{event.execution_id}"
            )
        if isinstance(event, PipelineRecoveredEvent):
            return (
                "⚠️ *Stale Execution Recovered*\n\n"
                f"*Recovered:*\n{event.recovered_execution_id}\n\n"
                f"*New Execution:*\n{event.execution_id}"
            )
        if isinstance(event, PipelineManualRunEvent):
            return (
                "▶️ *Daily Watchlist Manual Run Started*\n\n"
                f"*Trading Date:*\n{event.trading_date.isoformat()}\n\n"
                f"*Execution:*\n{event.execution_id}"
            )
        raise TypeError(f"Unsupported notification event: {type(event).__name__}")
