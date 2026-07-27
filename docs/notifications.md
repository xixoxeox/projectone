# Event-based notifications

## Architecture

Notifications are an application-boundary concern. The dependency direction is:

```text
DailyWatchlistPipeline
  -> PipelineResult
  -> NotificationPublishingPipeline
  -> NotificationEvent
  -> NotificationService
  -> NotificationProvider
  -> SlackNotificationProvider
  -> Slack Incoming Webhook
```

The pipeline returns structured state and never imports Slack code. The boundary adapter maps an outcome to a strongly typed success or failure event and, when applicable, emits a stale-execution recovery event first. `NotificationService` owns failure isolation and structured delivery logs. Formatting and HTTP transport belong exclusively to the selected provider.

The application composition root constructs one provider and injects its service. It reuses the application's lifespan-scoped `httpx.AsyncClient`; no client or connection pool is created per message.

## Providers and events

`NotificationProvider` is the async provider protocol. `SlackNotificationProvider` is the only external provider in Sprint 13. `NullNotificationProvider` deliberately discards events and is always selected when notifications are disabled.

Events contain data rather than presentation text:

- `PipelineSucceededEvent`
- `PipelineFailedEvent`
- `PipelineRecoveredEvent`
- `PipelineManualRunEvent`

Slack rendering stays in `SlackNotificationProvider`. Neither the pipeline nor `NotificationService` knows Slack's message format.

## Slack Incoming Webhook setup

1. In Slack, create or select a Slack app for the target workspace.
2. Open **Incoming Webhooks** in the app settings and enable the feature.
3. Select **Add New Webhook to Workspace**, select the desired destination, and authorize it.
4. Copy the generated URL beginning with `https://hooks.slack.com/services/`.
5. Put the URL in the backend `.env` file as `SLACK_WEBHOOK_URL`. Do not commit it.
6. Set `NOTIFICATION_ENABLED=true` and restart the API.

The repository does not hardcode a workspace or channel. Treat the webhook URL as a secret: rotate it through Slack immediately if it is exposed.

## Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `NOTIFICATION_ENABLED` | `false` | Enables external delivery. When false, the null provider is mandatory. |
| `NOTIFICATION_PROVIDER` | `slack` | Selected provider. Sprint 13 accepts only `slack`. |
| `SLACK_WEBHOOK_URL` | empty | Slack Incoming Webhook secret; required and validated when enabled. |
| `SLACK_TIMEOUT_SECONDS` | `10` | Per-attempt HTTP timeout; must be greater than zero and at most 60. |
| `SLACK_MAX_RETRIES` | `3` | Maximum total delivery attempts, from 1 through 3. |

## Retry and failure policy

Slack delivery makes at most three total attempts with delays of 1 and 2 seconds before the later attempts (the general backoff sequence is 1, 2, 4 seconds). Network errors, timeouts, and HTTP 5xx responses are retryable. HTTP 4xx responses—including 400, 401, 403, and 404—are terminal because they generally indicate payload, permission, or webhook configuration problems.

`NotificationService.publish()` catches and logs every provider exception. A notification outage therefore never changes a successful pipeline result and never masks a failed pipeline result. Delivery logs include provider, event type, delivery status, attempt metadata, and duration. They never include webhook URLs, tokens, secrets, request payloads, or authorization headers.

## Adding another provider

1. Implement `NotificationProvider.send(event)` in the notifications module.
2. Keep all provider-specific formatting and transport details in that implementation.
3. Extend the validated `notification_provider` setting with the new provider name.
4. Add one construction branch to `build_notification_service` at the composition root.
5. Add formatting, delivery, retry, and selection unit tests.

No pipeline logic or event model needs to change merely to add Discord, email, Teams, push, or another webhook transport. Those providers are intentionally not implemented in Sprint 13.
