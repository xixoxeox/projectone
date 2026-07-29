# Multi-setup swing screener v1

Sprint 19 reuses the persisted `stocks`/`daily_bars` → indicators → screening → scanning → ranking → watchlist pipeline. Bars are bulk-loaded in chronological symbol/date order through the target date; a symbol is evaluated only when its latest bar is exactly the target date. No live per-symbol provider request or future bar is used.

## Universe

Active, listed KOSPI common stocks require at least 61 bars, close ≥ ₩1,000, positive volume, SMA20/SMA60/ATR14, 20-day average `close × volume` ≥ ₩1bn, and ATR14/close ≤ 0.12. Stable exclusions are `inactive_security`, `unsupported_market`, `unsupported_security_type`, `missing_target_bar`, `insufficient_history`, `invalid_price`, `zero_volume`, `insufficient_liquidity`, `excessive_volatility`, and `missing_indicator`.

## Setups

* **Box breakout:** the target close breaks the previous (target excluded) 20-bar high from a box no wider than 15%, in an SMA20>SMA60 trend, above SMA20, with ≥1.2× prior volume and a non-bearish candle.
* **Trend pullback:** 3–12% below the prior 20-close peak, within 4% of EMA20, above SMA60 and the 98% SMA20 band, rebounding on a non-bearish candle while prior-five volume is ≤90% of prior-20 volume.
* **Volatility-contraction breakout:** the prior target-excluded ten-bar range is ≤8%, prior-five true range is ≤70% of prior-20, prior-five volume is ≤80% of prior-20, and the target breaks the range with ≥1.2× volume.

True range is `max(high-low, |high-previous close|, |low-previous close|)`. All arithmetic is `Decimal`. Setup scores are bounded 0–100 and rounded to 0.01 with `ROUND_HALF_UP`. Weights are box 35/30/35; pullback 35/30/20/15; contraction 30/25/20/25 as encoded in the immutable configuration.

A symbol may match multiple setups but produces one result. The highest setup score is primary; ties use volatility contraction, box breakout, pullback. Matched setups use that same order.

## Ranking and persistence

Swing ranking is trend 25%, setup 45%, liquidity 15%, volatility 15%. Ordering is total score descending, primary score descending, setup priority, then symbol. Consecutive ranks are truncated to 30 and persisted through the existing replace-on-save watchlist snapshot. Old snapshots default new fields to empty/null and backtests continue consuming one signal per row.

`GET /api/v1/screener/definitions` exposes the exact canonical v1 configuration. `/screener` uses persisted watchlist APIs; client filters use exact decimal-string comparison rather than floating point.

## Operations and limitations

The existing admin run, execution ownership, scheduler, notifications, and sync stages are reused. Technical conditions identify observation candidates and do not guarantee returns or initiate trades.

Limitations: daily bars only; no intraday confirmation; no order-book liquidity; no market-cap filter; no sector/theme classifications; no fundamentals; no corporate-action adjustment beyond existing data; no benchmark-relative strength; no automatic trading; fixed thresholds are not regime-optimized; KRX holidays are limited to persisted market dates.
