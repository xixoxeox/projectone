# Slack watchlist notifications

The canonical daily watchlist pipeline is wrapped by an event publisher. Successful persisted
watchlists emit `watchlist.published`; failed executions emit `watchlist.failed`. Skipped runs do
not notify. This decorator does not add another pipeline, scheduler, execution repository, or
database migration.

Set `SLACK_WEBHOOK_URL` to an incoming-webhook URL to enable Slack delivery. Configure each HTTP
attempt with `NOTIFICATION_TIMEOUT_SECONDS` (default 5) and retries with
`NOTIFICATION_MAX_RETRIES` (default 2). Retries use bounded exponential backoff. Provider errors
are logged without webhook contents, isolated from other providers, and never change the canonical
pipeline result. Leave the webhook unset to disable notifications.
