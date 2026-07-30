# Toss Securities Open API integration

## Contract source

Implementation was reviewed against the official [human documentation](https://developers.tossinvest.com/docs),
[AI-readable guide](https://developers.tossinvest.com/llms.txt), and canonical
[OpenAPI JSON](https://openapi.tossinvest.com/openapi-docs/latest/openapi.json).
The hosted OpenAPI document remains authoritative and is not vendored. Adapter
contract version: **1.2.5**. Server: `https://openapi.tossinvest.com`.

## KOSPI universe and maintenance

Toss does **not** enumerate the entire KOSPI market. The application loads the
reviewed, version-controlled KRX common-share snapshot at
`backend/data/kospi_common_stock_symbols.csv`, enriches its symbols through Toss
`/api/v1/stocks` in batches of at most 200, and obtains adjusted daily candles from
Toss.

To update the universe, export the listed-corporation report from the official KRX
Data Marketplace, retain active ordinary shares only, replace the CSV's single
`symbol` column, update `backend/data/README.md`, and run:

```bash
cd backend
python scripts/validate_kospi_universe.py data/kospi_common_stock_symbols.csv
```

Chart calls are deliberately throttled for `MARKET_DATA_CHART`. A first three-year
full-universe sync requires multiple backward pages per symbol and will take much
longer than an incremental sync; do not start concurrent sync jobs while it runs.

## Read-only mappings

| Official operation | Provider-neutral output |
| --- | --- |
| `POST /oauth2/token` | in-memory bearer token and expiry |
| `GET /api/v1/candles` | chronological `DailyBar` values |
| `GET /api/v1/prices` | `QuoteSnapshot` values |
| `GET /api/v1/stocks` | `InstrumentSnapshot` metadata |
| `GET /api/v1/stock-warnings` | `StockWarning` states |

OAuth uses a form-encoded `client_credentials` request. There is no refresh token.
Issuing a token invalidates the prior token, so all application requests share one
locked token manager. The adapter retries a market request only once after 401.

Prices use `Decimal`; delayed status is nullable because it is not invented when the
response lacks it. Candle prices and volume are non-negative, OHLC relationships and
timezone-aware timestamps are validated, dates are de-duplicated, and results sorted.

`Retry-After` is preferred for 429. `X-RateLimit-Reset` is interpreted as an epoch
fallback. Both are parsed defensively and waits are capped at 30 seconds. Transient
network errors, 429, and 5xx are bounded by `TOSS_MAX_RETRIES`; permanent 4xx are not.
The error envelope's safe code plus request ID may cross the adapter, never its raw
payload, credentials, bearer token, or headers.

Stock metadata is retained only where the official response supplies it: market,
country, currency, security type, listing status, and exchange. Later universe work
may exclude ETFs, ETNs, preferred shares, SPACs, or non-listed securities only when
these classification values are present. Names and symbol patterns are not used to
infer eligibility. Warning types are passed through as documented states, not inferred.

## Manual verification

Set real credentials and `ALLOW_LIVE_TOSS_SMOKE_TEST=true`, then run from `backend`:

```bash
python -m scripts.verify_toss_market_data --symbol 005930
```

The script prints safe summaries only. It is disabled by default and in CI. It calls
only the five read-only operations above. **No account or order API is implemented,
no account-selection header is sent, and no automatic trading code exists.**
