# Backtest foundation (PR #19)

> **“COMPLETED in PR #19 means the placeholder foundation execution completed successfully. It does not mean trades were simulated or strategy performance was validated.”**

`BacktestRun` stores `id`, `strategy_name`, optional `strategy_version`, `start_date`,
`end_date`, native PostgreSQL JSONB `parameters`, optional timezone-aware `data_as_of`,
`status`, lifecycle timestamps, and optional `failure_code` / `failure_message`. Nested
parameter objects and arrays are persisted directly, without application JSON encoding.

## Lifecycle, execution, and transactions

The only transitions are `PENDING → RUNNING → COMPLETED` and `RUNNING → FAILED`.
Repository transitions are conditional PostgreSQL updates with `RETURNING`; a missing ID
raises a typed not-found error and a stale or unexpected status raises a typed transition
error. This prevents concurrent callers from overwriting terminal state.

`BacktestService` owns transactions and deliberately commits after creation, after entering
`RUNNING`, and after the terminal transition. Executor work therefore never occurs in one
large transaction and a failure cannot erase observable lifecycle state. Executor exceptions
are logged, while persistence and clients receive only `BACKTEST_EXECUTION_FAILED` and the
safe message `Backtest execution failed`.

`BacktestExecutor.execute(run)` is the typed boundary for execution. The injected
`PlaceholderBacktestExecutor` returns an intentionally empty `BacktestExecutionResult`.
Placeholder execution validates the lifecycle boundary only. It does not simulate any trade.

## API

`POST /api/v1/backtests` accepts the strategy metadata, dates, JSON parameters, and
`data_as_of`; lifecycle and failure fields cannot be supplied. For example:

```json
{
  "strategy_name": "breakout",
  "strategy_version": "1.0",
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "data_as_of": "2026-07-28T00:00:00Z",
  "parameters": {
    "entry": "next_open",
    "risk": {"stop_loss_pct": 5, "take_profit_pct": 12},
    "filters": ["breakout", "volume"]
  }
}
```

`GET /api/v1/backtests/{run_id}` returns identical persisted metadata. The configured maximum
range is `BACKTEST_MAX_RANGE_DAYS=1825`. Invalid ranges return 422, missing runs return 404,
stale lifecycle transitions return 409, and safe execution failures return 500.

## Non-goals and PR #20

PR #19 contains no signals, historical reconstruction, entries/exits, position sizing,
trades, returns, performance analytics, equity curves, queues, or workers.

“PR #20 will replace the placeholder executor with a trade simulator without changing the BacktestService lifecycle contract.”
