# Market Data Provider Architecture

The market domain exposes provider-neutral instruments, daily bars, quotes, warnings,
and status models. Toss endpoint names and camel-case fields are confined to
`modules/market/infrastructure/toss.py`; HTTP handlers call `MarketDataService`.

The FastAPI lifespan owns one `httpx.AsyncClient`, one `TokenManager`, one provider,
and one service. The client is closed at shutdown. The token manager caches the only
valid client-credentials token in memory and locks issue/invalidation operations. A
401 invalidates the rejected cached token and permits exactly one issue-and-retry;
concurrent requests that rejected an older token cannot invalidate its replacement.

The adapter is **strictly read-only**. It has no account, holding, buying-power,
commission, order, conditional-order, or automatic-trading behavior and never sends
an account-selection header.

See [the verified contract mapping](docs/TOSS_API_INTEGRATION.md) for endpoints,
resilience decisions, and known metadata limitations.
