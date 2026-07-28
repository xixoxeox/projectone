# Daily watchlist scheduler

## Architecture and schedule

`DailyWatchlistPipeline` is the single orchestration service used by both APScheduler and the
authenticated manual API. It calls the established stock/daily-bar synchronization, indicator,
breakout screening, scanning, ranking, and watchlist repository components. It never places an
order. The lifespan-created `AsyncIOScheduler` registers one `daily-watchlist-pipeline` cron job
for Monday through Friday at **18:20 Asia/Seoul** by default; it does not run at startup. The hour,
minute, IANA timezone, enable flag, and positive misfire grace are configured with
`WATCHLIST_JOB_HOUR`, `WATCHLIST_JOB_MINUTE`, `WATCHLIST_JOB_TIMEZONE`, `SCHEDULER_ENABLED`, and
`WATCHLIST_JOB_MISFIRE_GRACE_SECONDS`. Scheduling is opt-in: `SCHEDULER_ENABLED` defaults to
`false`, and exactly one production process or container must explicitly set it to `true`.

The explicit stages are date resolution, duplicate check, market sync, indicator calculation,
screening, candidate scanning, ranking, atomic watchlist persistence, and completion. “Today” is
resolved in the configured timezone. Weekends are skipped. After synchronization, at least one
provider-confirmed daily bar must exist for the requested date; otherwise the run is safely
skipped. This is deterministic but is not a full KRX holiday calendar.

## Reliability and transactions

Execution history uses timezone-aware UTC timestamps and sanitized error metadata. A run is stale
when it remains `running` and `started_at` is older than the positive
`WATCHLIST_PIPELINE_STALE_AFTER_SECONDS` timeout (7200 seconds by default). Acquisition takes a
PostgreSQL two-key transaction advisory lock keyed by the documented watchlist namespace `1001`
and the trading-date ordinal. The namespace isolates this job family from future alert, report, or
sync schedulers that may also use date ordinals in PostgreSQL's database-wide advisory-lock space.
In that transaction acquisition inspects the active row, marks a stale row `failed` with `finished_at`,
`stale_execution_recovered`, and a sanitized detail, and inserts its replacement. Simultaneous
recovery attempts therefore produce one owner while retaining the abandoned run in history.

The partial unique index remains defense in depth: only one `running` or `succeeded` row can exist
per date. Failed and skipped rows permit retry; success prevents replacement. PostgreSQL tests
using independent sessions are required because SQLite cannot prove advisory-lock concurrency.
The required migration verification sequence is `alembic upgrade head`, `alembic downgrade -1`,
and `alembic upgrade head` against PostgreSQL. Advisory locks are runtime primitives and require no
schema migration; the sequence verifies that the partial active-execution index is recreated. CI
runs this sequence and the PostgreSQL integration suite against its PostgreSQL 17 service with
`TEST_DATABASE_URL`; local verification requires an equivalent reachable PostgreSQL database.

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

Responses exclude `error_detail`; stack information goes only to server logs. An active manual run
returns HTTP 409, while an already-completed date returns HTTP 200 with `already_completed`.
Validation uses HTTP 422 and failures expose only an error code. After a container kill, host
reboot, OOM, or worker crash, the first acquisition past the timeout finalizes the abandoned row
and starts a replacement; no history is deleted.

APScheduler is not distributed coordination. Production must enable scheduling on **exactly one**
instance. `docker compose --profile scheduler up` starts an optional scheduler-enabled API instance;
the normal `backend` service explicitly disables it. API-only instances and tests should set
`SCHEDULER_ENABLED=false` (test mode also suppresses startup). Shutdown through FastAPI lifespan
stops the scheduler cleanly. The optional service currently runs the same FastAPI image rather
than a standalone scheduler command; this avoids a second dependency/bootstrap path but means it
also exposes an un-published internal HTTP server.
