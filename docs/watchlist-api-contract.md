# Watchlist frontend API contract

The dashboard uses the configured `NEXT_PUBLIC_API_BASE_PATH` (default `/api/v1` for same-origin local/proxied development). No deployment URL is embedded in the client.

## Endpoints

- `GET /watchlist/latest`: summary array for the latest persisted date; `[]` is a valid empty state.
- `GET /watchlist/history`: ISO `YYYY-MM-DD` date array. The UI defensively sorts newest first.
- `GET /watchlist/{trading_date}`: summary array, or `404` when unavailable.
- `GET /watchlist/{trading_date}/{symbol}`: one detail item, or `404` when unavailable.

Summary items contain `rank`, `symbol`, `total_score`, `component_scores`, and ranking `warnings`. Detail items additionally contain `trading_date`, `snapshot`, `metrics`, and `reasons`. Screening `passed`, metrics, reasons, and warnings belong to the detail-only snapshot; persistence identifiers are never displayed.

## Precision and display

Every Decimal is received and retained as a string. The UI never converts it to a JavaScript number. For display only, the deterministic formatter removes trailing zeroes from the fractional part and removes an empty fractional part. It preserves all other digits: `91.120000` becomes `91.12`, `91.000000` becomes `91`, and `0.12345678901234567890` becomes `0.1234567890123456789`.

## Navigation and failures

The selected date is represented as `/watchlist?date=YYYY-MM-DD`. Updating it uses Next.js navigation so history and browser back/forward remain useful; detail routes are `/watchlist/{trading_date}/{symbol}`. An empty latest array is not an error. A selected-date/detail `404` gets a Korean not-found state; validation, server, and network failures get a safe message and retry action without exposing backend details.

## Local development

Set `NEXT_PUBLIC_API_BASE_PATH` only when the backend is not available at the default same-origin `/api/v1` path, then run `npm run dev` from `frontend`. Do not include a trailing slash and do not commit secrets.
