# Daily watchlist scheduler

## Architecture and schedule

`DailyWatchlistPipeline` is the single orchestration service used by both APScheduler and the
authenticated manual API. It calls the established stock/daily-bar synchronization, indicator,
breakout screening, scanning, ranking, and watchlist repository components. It never places an
order. The lifespan-created `AsyncIOScheduler` registers one `daily-watchlist-pipeline` cron job
for Monday through Friday at **18:20 Asia/Seoul** by default; it does not run at startup. The hour,
minute, IANA timezone, enable flag, and positive misfire grace are configured with
`WATCHLIST_JOB_HOUR`, `WATCHLIST_JOB_MINUTE`, `WATCHLIST_JOB_TIMEZONE`, `SCHEDULER_ENABLED`, and
`WATCHLIST_JOB_MISFIRE_GRACE_SECONDS`.

The explicit stages are date resolution, duplicate check, market sync, indicator calculation,
screening, candidate scanning, ranking, atomic watchlist persistence, and completion. “Today” is
resolved in the configured timezone. Weekends are skipped. After synchronization, at least one
provider-confirmed daily bar must exist for the requested date; otherwise the run is safely
skipped. This is deterministic but is not a full KRX holiday calendar.

## Reliability and transactions

Execution history is stored in `watchlist_pipeline_executions` with timezone-aware timestamps and
sanitized error metadata. A PostgreSQL partial unique index permits only one `running` or
`succeeded` row per trading date. Inserting the running row is the database-backed ownership
operation, so competing workers and instances lose safely. Failed and skipped rows do not prevent
a later retry. The successful row prevents accidental replacement. This depends on PostgreSQL;
SQLite tests cannot prove its distributed concurrency behavior.

Transactions are deliberately short: ownership/history creation commits first, provider and CPU
work occurs afterward, watchlist replacement commits atomically only after all ranked results are
ready, and completion is recorded separately. Failure is recorded in a fresh session. Existing
watchlists therefore survive upstream or calculation failures. An empty passing candidate set is
recorded as `skipped/no_candidates` and does not replace a valid watchlist. Decimal scoring and rank
order continue through the existing ranking and repository implementations unchanged.

There is no whole-pipeline retry loop. Provider retries retain their existing bounded policy; a
failed run remains visible and an administrator may retry it manually.

## Operations and APIs

All endpoints require the existing administrator bearer authentication:

* `POST /api/v1/admin/watchlist/run` (optional JSON `trading_date`)
* `GET /api/v1/admin/watchlist/executions/latest`
* `GET /api/v1/admin/watchlist/executions?limit=50`
* `GET /api/v1/admin/watchlist/executions/{execution_id}`

Responses exclude `error_detail`; internal exception types are retained only as sanitized
operational metadata and stack information goes only to server logs. Concurrent/completed manual
runs return HTTP 409, validation uses HTTP 422, and pipeline failures expose only an error code.

APScheduler is not distributed coordination. Production must enable scheduling on **exactly one**
instance. `docker compose --profile scheduler up` starts the optional scheduler-enabled backend;
the normal `backend` service explicitly disables it. API-only instances and tests should set
`SCHEDULER_ENABLED=false` (test mode also suppresses startup). Shutdown through FastAPI lifespan
stops the scheduler cleanly. The optional service currently runs the same FastAPI image rather
than a standalone scheduler command; this avoids a second dependency/bootstrap path but means it
also exposes an un-published internal HTTP server.
