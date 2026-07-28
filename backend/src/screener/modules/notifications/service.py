import asyncio
import logging
from collections.abc import Sequence
from typing import Protocol

from .events import NotificationEvent

logger = logging.getLogger(__name__)


class NotificationProvider(Protocol):
    async def publish(self, event: NotificationEvent) -> None: ...


class NotificationService:
    """Fan events out without allowing one delivery to affect another."""

    def __init__(self, providers: Sequence[NotificationProvider]) -> None:
        self.providers = list(providers)

    async def publish(self, event: NotificationEvent) -> None:
        results = await asyncio.gather(
            *(provider.publish(event) for provider in self.providers), return_exceptions=True
        )
        for provider, result in zip(self.providers, results, strict=True):
            if isinstance(result, BaseException):
                logger.error(
                    "notification_delivery_failed provider=%s event=%s error=%s",
                    type(provider).__name__,
                    event.type,
                    type(result).__name__,
                )
