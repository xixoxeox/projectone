from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from screener.modules.market.pipeline import ExecutionStatus, PipelineResult, PipelineStage
from screener.modules.notifications import (
    NotificationEvent,
    NotificationEventType,
    NotificationPublishingPipeline,
    NotificationService,
    SlackNotificationProvider,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def result(status: ExecutionStatus) -> PipelineResult:
    return PipelineResult(
        trading_date=date(2026, 7, 28),
        status=status,
        started_at=datetime.now(UTC),
        stage=PipelineStage.COMPLETED,
        persisted_count=3,
        error_code="screening_failed" if status == ExecutionStatus.FAILED else None,
    )


@pytest.mark.parametrize(
    ("status", "event_type"),
    [
        (ExecutionStatus.SUCCEEDED, NotificationEventType.WATCHLIST_PUBLISHED),
        (ExecutionStatus.FAILED, NotificationEventType.WATCHLIST_FAILED),
    ],
)
async def test_pipeline_publishes_terminal_event(status: ExecutionStatus, event_type: str) -> None:
    pipeline = AsyncMock()
    pipeline.run.return_value = result(status)
    notifications = AsyncMock()

    actual = await NotificationPublishingPipeline(pipeline, notifications).run()

    assert actual.status == status
    event = notifications.publish.await_args.args[0]
    assert event.type == event_type
    assert event.candidate_count == 3


async def test_pipeline_does_not_publish_skipped_run() -> None:
    pipeline, notifications = AsyncMock(), AsyncMock()
    pipeline.run.return_value = result(ExecutionStatus.SKIPPED)
    await NotificationPublishingPipeline(pipeline, notifications).run()
    notifications.publish.assert_not_awaited()


async def test_notification_failure_is_isolated_from_pipeline_result() -> None:
    pipeline, notifications = AsyncMock(), AsyncMock()
    expected = result(ExecutionStatus.SUCCEEDED)
    pipeline.run.return_value = expected
    notifications.publish.side_effect = RuntimeError("delivery failed")
    assert await NotificationPublishingPipeline(pipeline, notifications).run() == expected


async def test_service_isolates_providers() -> None:
    failing, succeeding = AsyncMock(), AsyncMock()
    failing.publish.side_effect = RuntimeError("nope")
    event = NotificationEvent(
        type=NotificationEventType.WATCHLIST_PUBLISHED, trading_date=date(2026, 7, 28)
    )
    await NotificationService([failing, succeeding]).publish(event)
    succeeding.publish.assert_awaited_once_with(event)


async def test_slack_retries_transient_failure() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503 if attempts == 1 else 200, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = SlackNotificationProvider(client, "https://hooks.slack.test/1", max_retries=1)
        await provider.publish(
            NotificationEvent(
                type=NotificationEventType.WATCHLIST_PUBLISHED,
                trading_date=date(2026, 7, 28),
                candidate_count=2,
            )
        )
    assert attempts == 2


async def test_slack_stops_after_retry_budget() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request))
    ) as client:
        provider = SlackNotificationProvider(client, "https://hooks.slack.test/1", max_retries=1)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.publish(
                NotificationEvent(
                    type=NotificationEventType.WATCHLIST_FAILED,
                    trading_date=date(2026, 7, 28),
                )
            )
