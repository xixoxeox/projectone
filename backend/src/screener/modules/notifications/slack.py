import asyncio

import httpx

from .events import NotificationEvent, NotificationEventType


class SlackNotificationProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        webhook_url: str,
        *,
        timeout_seconds: float = 5,
        max_retries: int = 2,
    ) -> None:
        self.client = client
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    async def publish(self, event: NotificationEvent) -> None:
        text = self._text(event)
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.post(
                    self.webhook_url, json={"text": text}, timeout=self.timeout_seconds
                )
                response.raise_for_status()
                return
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if 400 <= status < 500 and status != 429:
                    raise
                if attempt == self.max_retries:
                    raise
                await asyncio.sleep(0.25 * (2**attempt))
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == self.max_retries:
                    raise
                await asyncio.sleep(0.25 * (2**attempt))

    @staticmethod
    def _text(event: NotificationEvent) -> str:
        if event.type == NotificationEventType.WATCHLIST_PUBLISHED:
            return (
                f"Watchlist published for {event.trading_date}: "
                f"{event.candidate_count or 0} candidates"
            )
        return (
            f"Watchlist pipeline failed for {event.trading_date}: {event.error_code or 'unknown'}"
        )
