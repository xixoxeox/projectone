# Individual real-time stock analysis

## Scope

`/analysis` is an authenticated, read-only KOSPI common-stock analysis screen. A user
enters a six-character symbol and receives the latest request-time chart and a
deterministic technical interpretation. It does not submit orders and does not alter
the scheduled screener or watchlist.

The backend endpoint is:

```text
GET /api/v1/instruments/{symbol}/analysis
```

Only instruments whose provider metadata says `KOSPI`, `common_stock`, and `listed`
are accepted. Missing symbols return 404, invalid or unsupported symbols return 422,
and provider availability failures retain the existing sanitized error mapping.

## Data and calculations

One request reads the current quote, daily candles for the last 240 calendar days,
the latest 200 official one-minute candles, and current warning states. One-minute
candles remain unchanged; 5-minute and 10-minute candles are grouped by
`Asia/Seoul` wall-clock buckets with first open, maximum high, minimum low, last
close, and summed volume.

The response includes:

- daily trend, SMA20, SMA60, EMA20, ATR percentage, and prior 20-session range;
- the existing multi-setup screener result and configured score threshold;
- per-timeframe SMA5, SMA20, session VWAP, five-candle momentum, volume ratio, and
  recent range;
- up to three nearby support and resistance candidates, each with its calculation
  basis;
- a deterministic verdict, observations, confirmation condition, invalidation
  condition, warning-derived and quantitative risk flags;
- chart-ready daily and 1-, 5-, and 10-minute OHLCV arrays.

A total screener score is returned only when the daily setup actually passes. The
response exposes the last daily candle's trading date as the screener evaluation
date, and never invents a partial score for an incomplete setup.

## Refresh and limitations

The UI defaults to 5-minute candles. Automatic refresh runs every 60 seconds only
while the document is visible; manual refresh is also available. A failed refresh
shows an error while preserving the last successful analysis.

Toss currently supplies request/response candles here rather than a websocket
stream. The newest one-minute candle may still be in progress, so its high, low,
close, and volume can change. Support, resistance, confirmation, and invalidation
are technical candidates, not guaranteed prices or investment advice.
