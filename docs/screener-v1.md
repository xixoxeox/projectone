# Multi-setup swing screener v1

Sprint 19 keeps the existing sync → indicators → screening → scanning → ranking → watchlist pipeline. It evaluates canonical active, listed KOSPI common stocks using only persisted daily bars.

## Configuration and filters

`SwingScreeningConfig` is immutable and is the single source for history, liquidity, volatility, lookback, scoring, and candidate-limit defaults. Common filters require a target bar, 61 bars, a positive-volume close of at least KRW 1,000, SMA20/SMA60/ATR14, twenty-bar average trading value of KRW 1 billion, and ATR/close no greater than 0.12.

## Setups and scoring

Box breakout compares the target close and volume with a target-excluded price box and volume mean. Trend pullback measures peak-to-close depth, EMA20 proximity, prior short-volume contraction, and rebound body. Volatility-contraction breakout uses a target-excluded range, gap-aware true ranges, long/short volume baselines, and breakout volume. Scores are bounded 0–100 Decimals, rounded half-up to 0.01; component weights are 35/30/35, 35/30/20/15, and 30/25/20/25 respectively.

Ranking weights trend/setup/liquidity/volatility by 25/45/15/15. Ties use total score, primary score, `volatility_contraction_breakout`, `box_breakout`, `trend_pullback`, then symbol. Ranks are consecutive.

## Data and API

Persisted loading is bounded to the newest configured N rows per symbol through the target date; calendar intervals and future bars are not used. A successful execution with zero persisted candidates is an authoritative empty result. `/api/v1/screener/definitions` describes exact string Decimal defaults. Watchlist snapshots remain compatible when older records omit v1 fields. The `/screener` UI stores date, setup, query, thresholds, warning flag, and sort state in URL parameters without floating-point financial comparisons.

## Limitations

Daily bars only; no intraday confirmation, order-book data, market capitalization, sector/theme classification, fundamentals, benchmark-relative strength, automatic trading, or assurance of future returns. Technical conditions do not guarantee future returns.
