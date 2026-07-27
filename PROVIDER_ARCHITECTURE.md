# Market Data Provider Architecture

## Boundary

The market domain exposes provider-neutral, validated models for provider status,
instruments, daily bars, and quotes. `MarketDataService` validates date ranges and
symbols and adds source, freshness, timezone, and stale metadata. HTTP handlers depend
on that service rather than Toss.

The Toss adapter is read-only. It contains HTTP, authorization, retry, error
normalization, and upstream-to-domain mapping. It contains **no account, order, or
automatic-trading code**, and access tokens are cached only in process memory.

## Deliberately blocked official details

No approved repository document contains an official Toss Securities Open API
specification. Therefore the production adapter does not guess any of the following:

1. OAuth/token endpoint, grant payload, scopes, response field names, or refresh rules.
2. Daily-bar or instrument endpoint paths and query parameter names.
3. Upstream response envelopes, bar field names, pagination, limits, timezone, or
   quote/calendar availability.
4. Official production host and rate-limit policy.

`TossApiSpecification` is the isolated seam for confirmed paths and mappings. Until an
official, versioned specification answers these questions, the configured provider
reports `unavailable` and data calls fail safely. Quote, search, and calendar endpoints
are consequently not exposed.

## Authentication and resilience

`TokenManager` receives an isolated, spec-specific issuer, keeps the bearer token only
in memory, refreshes before expiry with configurable skew, and uses an async lock to
coalesce concurrent refreshes. The adapter uses explicit `httpx` timeouts, retries only
timeouts/network errors, 429, and 5xx responses, honors bounded `Retry-After`, and never
retries 401/403 or other 4xx responses. Errors never include response bodies, request
headers, client secrets, or tokens.

## Configuration and local verification

Copy `.env.example`; credentials are required at production settings validation but are
not needed by tests. Run `cd backend && pytest`. Tests use `httpx.MockTransport` and
injected mappings, so they make no network requests and do not imply that a live Toss
contract has been confirmed.
