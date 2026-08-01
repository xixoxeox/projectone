# Multi-setup swing screener v1

## Architecture and universe

Sprint 19 retains the single sync → indicator calculation → screening → scanning → ranking → watchlist persistence pipeline. A single bounded SQL window query selects persisted bars only for active `KOSPI`, `listed`, `common_stock` stock-master rows. It partitions by symbol, orders trading dates descending, limits each symbol to `minimum_history_bars`, excludes future bars, then restores deterministic symbol/date order. A target-date bar is mandatory.

Common filtering requires 61 bars; close ≥ KRW 1,000; positive latest volume; SMA20, SMA60, and ATR14; 20-bar average `close × volume` ≥ KRW 1 billion; and ATR14/latest close ≤ 0.12. No market-capitalization, sector, industry, or theme values are invented.

## Configuration

`SwingScreeningConfig` is immutable and is shared by strategies, common filtering, ranking liquidity, candidate limiting, and definitions. It validates positive lookbacks, short/long relationships, and enough history for every accepted window. The final-candidate defaults are `minimum_candidate_score=80` and `maximum_candidates=5`. Decimal defaults are serialized as exact strings.

## Setups, windows, and formulas

Every “previous” window excludes the target bar.

* **Box breakout:** prior 20-bar high/low and mean volume. `box_width_pct=(high-low)/high`, `breakout_pct=(close-high)/high`, and `volume_ratio=latest_volume/prior_mean_volume`. Tightness is 100 through 0.05, linearly declines, and is 0 at 0.15. Score weights are tightness 35%, breakout distance 30%, volume expansion 35%.
* **Trend pullback:** prior 20-bar peak close and mean volume plus an independently configured prior 5-bar short-volume mean. `depth=(peak-close)/peak`, `EMA distance=abs(close-EMA20)/EMA20`, and short-volume ratio is short mean/long mean. The latest volume is excluded. Score weights are depth quality 35%, EMA proximity 30%, volume contraction 20%, rebound body 15%.
* **Volatility-contraction breakout:** prior 10-bar range, prior 20-bar volumes, and 20 gap-aware true ranges where `TR=max(high-low,abs(high-previous_close),abs(low-previous_close))`. Short averages use the final five target-excluded values. Range tightness is 100 through 0.03, linearly declines, and is 0 at 0.08. Score weights are range 30%, TR contraction 25%, volume contraction 20%, breakout volume 25%.

Scores use finite `Decimal` values, explicit zero-denominator policies, 0–100 clamping, and `ROUND_HALF_UP` quantization to 0.01. All setup metrics and rule outcomes remain auditable, but `setup_scores` and ranking include passing setups only.

## Ranking and persistence

Ranking weights trend/setup/liquidity/volatility 25/45/15/15. Setup is the maximum passing matched score. Ties use total score, primary matched score, canonical priority (`volatility_contraction_breakout`, `box_breakout`, `trend_pullback`), then symbol. Symbols are unique and ranks consecutive. After ranking, scores below `minimum_candidate_score` are excluded and only the first `maximum_candidates` qualified rows are persisted.

The latest successful row in `watchlist_pipeline_executions` is authoritative. Each new execution records the number screened, the number passing a setup, the number meeting the score threshold, the threshold itself, and the final persisted count. A succeeded execution with `persisted_count=0` is a real empty result: it appears in history, date and latest reads return `[]`, and candidates from older dates cannot leak. Failed executions are excluded; dates without a success return 404; missing symbol detail returns 404. Replacement is transactional.

## API and frontend

Authenticated `GET /api/v1/screener/definitions` returns name, version, setup keys, Korean labels, descriptions, exact defaults, and limitations. `GET /api/v1/screener/results/{trading_date}` combines the authoritative successful execution funnel with that date's watchlist items. Older execution rows remain readable with nullable funnel fields. Compact watchlist data exposes common metrics plus only the primary setup's appropriate volume metrics. Detail adds setup scores, setup metrics, grouped rule evaluations, and configuration snapshot. Historical snapshots with absent v1 fields retain defaults.

`/screener` loads definitions, successful history, the selected result envelope, latest execution metadata, and uses the existing administrative run endpoint. When no row reaches the score threshold, the UI states how many symbols were screened, the exact threshold, and that an empty list is a normal result rather than an error or forced recommendation. A non-empty base result that becomes empty only after local filtering gets a separate state and filter-reset action. URL keys are `date`, `setup`, `q`, `minScore`, `minValue`, `warningFree`, and `sort`; changes preserve unrelated keys. Empty values are removed, numeric-filter zero is the default, `warningFree` persists only as `1`, and rank is the default sort. Searches such as `q=0`, `q=005930`, and `q=rank` remain strings. Financial comparisons and percentage rendering operate on exact decimal strings rather than JavaScript numbers.

## Compatibility and limitations

The legacy `BreakoutStrategy`, pipeline, scheduler, notifications, and historical snapshots remain compatible. Migration `0009_screening_summary` adds nullable funnel fields to existing execution rows. Scheduled screening remains daily-bar based. Individual request-time chart analysis is documented in [`realtime-stock-analysis.md`](realtime-stock-analysis.md); it does not change watchlist selection. There is no automatic trading. Limitations include no order-book data, market capitalization, sector/theme classification, fundamentals, benchmark-relative strength, websocket stream, or return guarantee. Technical conditions do not guarantee future returns.
