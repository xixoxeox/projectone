from datetime import date

import httpx
import pytest
from pydantic import ValidationError

from screener.config import Settings
from screener.modules.notifications import (
    NotificationPublishingPipeline,
    NotificationService,
    NullNotificationProvider,
    PipelineFailedEvent,
    PipelineRecoveredEvent,
    PipelineResult,
    PipelineSucceededEvent,
    SlackNotificationProvider,
    TriggerType,
    build_notification_service,
)

WEBHOOK = "https://hooks.slack.com/services/T000/B000/secret"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def success_event() -> PipelineSucceededEvent:
    return PipelineSucceededEvent(
        trading_date=date(2026, 7, 28),
        execution_id="exec-1",
        trigger_type=TriggerType.SCHEDULED,
        candidate_count=18,
        persisted_count=18,
        duration_seconds=24.2,
    )


def test_disabled_always_selects_null_provider() -> None:
    settings = Settings(notification_enabled=False, slack_webhook_url=None)
    service = build_notification_service(settings, httpx.AsyncClient())
    assert isinstance(service.provider, NullNotificationProvider)


def test_enabled_selects_slack_provider() -> None:
    settings = Settings(notification_enabled=True, slack_webhook_url=WEBHOOK)
    service = build_notification_service(settings, httpx.AsyncClient())
    assert isinstance(service.provider, SlackNotificationProvider)


@pytest.mark.anyio
async def test_null_provider_does_nothing() -> None:
    await NullNotificationProvider().send(success_event())


def test_slack_formats_structured_success_event() -> None:
    message = SlackNotificationProvider.format_event(success_event())
    assert "Daily Watchlist Completed" in message
    assert "2026-07-28" in message
    assert "18" in message
    assert "24.2 sec" in message
    assert "exec-1" in message


@pytest.mark.anyio
async def test_retry_delays_are_exponential_for_5xx() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503 if attempts < 3 else 200)

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await SlackNotificationProvider(client, WEBHOOK, sleep=sleep).send(success_event())
    assert attempts == 3
    assert delays == [1.0, 2.0]


@pytest.mark.anyio
async def test_no_retry_on_4xx() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(403)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await SlackNotificationProvider(client, WEBHOOK).send(success_event())
    assert attempts == 1


@pytest.mark.anyio
async def test_retry_on_timeout() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200)

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await SlackNotificationProvider(client, WEBHOOK, sleep=sleep).send(success_event())
    assert attempts == 2
    assert delays == [1.0]


class RaisingProvider:
    name = "broken"

    async def send(self, event: object) -> None:
        raise RuntimeError("transport down")


@pytest.mark.anyio
async def test_notification_exception_does_not_fail_pipeline() -> None:
    expected = PipelineResult(date(2026, 7, 28), "exec-1", TriggerType.SCHEDULED, True)

    async def pipeline() -> PipelineResult:
        return expected

    wrapper = NotificationPublishingPipeline(pipeline, NotificationService(RaisingProvider()))
    assert await wrapper.run() is expected


class RecordingProvider:
    name = "recording"

    def __init__(self) -> None:
        self.events: list[object] = []

    async def send(self, event: object) -> None:
        self.events.append(event)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("result", "event_types"),
    [
        (
            PipelineResult(date(2026, 7, 28), "new", TriggerType.SCHEDULED, True),
            [PipelineSucceededEvent],
        ),
        (
            PipelineResult(
                date(2026, 7, 28),
                "new",
                TriggerType.SCHEDULED,
                False,
                stage="ranking",
                error_code="ranking_failed",
            ),
            [PipelineFailedEvent],
        ),
        (
            PipelineResult(
                date(2026, 7, 28),
                "new",
                TriggerType.SCHEDULED,
                True,
                recovered_execution_id="stale",
            ),
            [PipelineRecoveredEvent, PipelineSucceededEvent],
        ),
    ],
)
async def test_pipeline_publishes_outcome_events(
    result: PipelineResult, event_types: list[type[object]]
) -> None:
    provider = RecordingProvider()

    async def pipeline() -> PipelineResult:
        return result

    returned = await NotificationPublishingPipeline(pipeline, NotificationService(provider)).run()
    assert returned is result
    assert [type(event) for event in provider.events] == event_types


def test_enabled_slack_requires_webhook() -> None:
    with pytest.raises(ValidationError, match="SLACK_WEBHOOK_URL is required"):
        Settings(notification_enabled=True, slack_webhook_url=None)


@pytest.mark.parametrize(
    "url", ["http://hooks.slack.com/services/a/b/c", "https://example.com/hook"]
)
def test_webhook_url_validation(url: str) -> None:
    with pytest.raises(ValidationError, match="Slack Incoming Webhook URL"):
        Settings(notification_enabled=True, slack_webhook_url=url)


def test_settings_validate_retry_and_timeout_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings(slack_max_retries=4)
    with pytest.raises(ValidationError):
        Settings(slack_timeout_seconds=0)
