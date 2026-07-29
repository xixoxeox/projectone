"""Versioned, pure Decimal multi-setup swing screening."""

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.models import IndicatorSnapshot
from screener.modules.market.screening.models import ScreeningResult

D = Decimal
ZERO = D("0")
HUNDRED = D("100")
Q = D("0.01")


class SwingSetup(StrEnum):
    BOX_BREAKOUT = "box_breakout"
    TREND_PULLBACK = "trend_pullback"
    VOLATILITY_CONTRACTION_BREAKOUT = "volatility_contraction_breakout"


PRIORITY = (
    SwingSetup.VOLATILITY_CONTRACTION_BREAKOUT,
    SwingSetup.BOX_BREAKOUT,
    SwingSetup.TREND_PULLBACK,
)


class SwingScreeningConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    screener_name: str = "multi_setup_swing"
    screener_version: str = "1"
    minimum_history_bars: int = 61
    minimum_close: Decimal = D("1000")
    minimum_average_trading_value_20: Decimal = D("1000000000")
    maximum_atr_pct: Decimal = D("0.12")
    maximum_candidates: int = 30
    box_lookback: int = 20
    maximum_box_width_pct: Decimal = D("0.15")
    minimum_breakout_volume_ratio: Decimal = D("1.20")
    maximum_scored_breakout_pct: Decimal = D("0.05")
    maximum_scored_volume_ratio: Decimal = D("3.00")
    pullback_lookback: int = 20
    pullback_volume_lookback: int = 5
    minimum_pullback_depth_pct: Decimal = D("0.03")
    ideal_pullback_depth_pct: Decimal = D("0.06")
    maximum_pullback_depth_pct: Decimal = D("0.12")
    maximum_ema20_distance_pct: Decimal = D("0.04")
    maximum_prior5_volume_ratio: Decimal = D("0.90")
    best_prior5_volume_ratio: Decimal = D("0.50")
    maximum_scored_rebound_body_pct: Decimal = D("0.03")
    contraction_range_lookback: int = 10
    contraction_short_lookback: int = 5
    contraction_long_lookback: int = 20
    maximum_contraction_range_pct: Decimal = D("0.08")
    maximum_true_range_contraction_ratio: Decimal = D("0.70")
    best_true_range_contraction_ratio: Decimal = D("0.40")
    contraction_maximum_prior5_volume_ratio: Decimal = D("0.80")
    contraction_best_prior5_volume_ratio: Decimal = D("0.50")
    maximum_scored_breakout_volume_ratio: Decimal = D("3.00")

    @model_validator(mode="after")
    def valid_lookbacks(self) -> "SwingScreeningConfig":
        lookbacks = (
            self.box_lookback,
            self.pullback_lookback,
            self.pullback_volume_lookback,
            self.contraction_range_lookback,
            self.contraction_short_lookback,
            self.contraction_long_lookback,
        )
        if any(value <= 0 for value in lookbacks):
            raise ValueError("all lookbacks must be positive")
        if self.contraction_short_lookback > self.contraction_long_lookback:
            raise ValueError("contraction_short_lookback must not exceed long lookback")
        if self.pullback_volume_lookback > self.pullback_lookback:
            raise ValueError("pullback_volume_lookback must not exceed pullback lookback")
        required = max(
            20,
            self.box_lookback + 1,
            self.pullback_lookback + 1,
            self.pullback_volume_lookback + 1,
            self.contraction_range_lookback + 1,
            self.contraction_long_lookback + 2,
        )
        if self.minimum_history_bars < required:
            raise ValueError(f"minimum_history_bars must be at least {required}")
        return self


CONFIG = SwingScreeningConfig()


def clamp_score(v: Decimal) -> Decimal:
    if not v.is_finite():
        raise ValueError("score input must be finite")
    return min(HUNDRED, max(ZERO, v))


def quantize_score(v: Decimal) -> Decimal:
    return clamp_score(v).quantize(Q, rounding=ROUND_HALF_UP)


def high_is_good(v: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    if maximum <= minimum:
        raise ValueError("invalid score range")
    return quantize_score((v - minimum) / (maximum - minimum) * HUNDRED)


def low_is_good(v: Decimal, best: Decimal, worst: Decimal) -> Decimal:
    if worst <= best:
        raise ValueError("invalid score range")
    return quantize_score((worst - v) / (worst - best) * HUNDRED)


def triangular_score(v: Decimal, lower: Decimal, ideal: Decimal, upper: Decimal) -> Decimal:
    if not lower < ideal < upper:
        raise ValueError("invalid triangular range")
    return high_is_good(v, lower, ideal) if v <= ideal else low_is_good(v, ideal, upper)


def avg(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ValueError("average requires values")
    return sum(values, ZERO) / D(len(values))


def true_range(bar: DailyBar, previous_close: Decimal) -> Decimal:
    return max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close))


def common_metrics(bars: Sequence[DailyBar], i: IndicatorSnapshot) -> dict[str, Decimal]:
    latest = bars[-1]
    values = [bar.close * D(bar.volume) for bar in bars[-20:]]
    result = {
        "close": latest.close,
        "open": latest.open,
        "volume": D(latest.volume),
        "average_trading_value_20": avg(values),
    }
    for name in ("sma20", "sma60", "ema20", "atr14"):
        value = getattr(i, name)
        if value is not None:
            result[name] = value
    if i.atr14 is not None and latest.close > 0:
        result["atr_pct"] = i.atr14 / latest.close
    return result


def _result(
    setup: SwingSetup,
    bars: Sequence[DailyBar],
    metrics: dict[str, Decimal],
    rules: dict[str, bool],
    score: Decimal,
) -> ScreeningResult:
    passed = all(rules.values())
    reasons = [f"{'PASSED' if ok else 'FAILED'}: {name}" for name, ok in rules.items()]
    return ScreeningResult(
        symbol=bars[-1].symbol if bars else "",
        passed=passed,
        reasons=reasons,
        metrics=metrics,
        rule_evaluations=rules,
        matched_setups=[setup] if passed else [],
        primary_setup=setup if passed else None,
        setup_scores={setup: score} if passed else {},
        setup_metrics={setup: metrics},
        evaluated_setup=setup,
    )


class BoxBreakoutStrategy:
    def __init__(self, config: SwingScreeningConfig = CONFIG):
        self.c = config

    def evaluate(self, bars: Sequence[DailyBar], i: IndicatorSnapshot) -> ScreeningResult:
        if len(bars) < self.c.box_lookback + 1:
            return ScreeningResult(
                symbol=bars[-1].symbol if bars else "",
                passed=False,
                reasons=["FAILED: insufficient_history"],
            )
        latest = bars[-1]
        prior = bars[-(self.c.box_lookback + 1) : -1]
        hi = max(x.high for x in prior)
        lo = min(x.low for x in prior)
        av = avg([D(x.volume) for x in prior])
        m = common_metrics(bars, i)
        m.update(
            previous_box_high=hi,
            previous_box_low=lo,
            box_width_pct=(hi - lo) / hi if hi else ZERO,
            breakout_pct=(latest.close - hi) / hi if hi else ZERO,
            previous_average_volume=av,
            volume_ratio=D(latest.volume) / av if av else ZERO,
        )
        rules = {
            "trend": i.sma20 is not None and i.sma60 is not None and i.sma20 > i.sma60,
            "above_sma20": i.sma20 is not None and latest.close > i.sma20,
            "positive_previous_high": hi > 0,
            "box_width": m["box_width_pct"] <= self.c.maximum_box_width_pct,
            "breakout": latest.close >= hi,
            "volume_expansion": m["volume_ratio"] >= self.c.minimum_breakout_volume_ratio,
            "bullish_candle": latest.close >= latest.open,
        }
        score = quantize_score(
            low_is_good(m["box_width_pct"], D(".05"), D(".15")) * D(".35")
            + high_is_good(m["breakout_pct"], ZERO, self.c.maximum_scored_breakout_pct) * D(".30")
            + high_is_good(
                m["volume_ratio"],
                self.c.minimum_breakout_volume_ratio,
                self.c.maximum_scored_volume_ratio,
            )
            * D(".35")
        )
        return _result(SwingSetup.BOX_BREAKOUT, bars, m, rules, score)


class TrendPullbackStrategy:
    def __init__(self, config: SwingScreeningConfig = CONFIG):
        self.c = config

    def evaluate(self, bars: Sequence[DailyBar], i: IndicatorSnapshot) -> ScreeningResult:
        required = max(self.c.pullback_lookback, self.c.pullback_volume_lookback) + 1
        if len(bars) < required:
            return ScreeningResult(
                symbol=bars[-1].symbol if bars else "",
                passed=False,
                reasons=["FAILED: insufficient_history"],
            )
        latest = bars[-1]
        prior = bars[-(self.c.pullback_lookback + 1) : -1]
        peak = max(x.close for x in prior)
        av = avg([D(x.volume) for x in prior])
        p5 = avg([D(x.volume) for x in bars[-(self.c.pullback_volume_lookback + 1) : -1]])
        m = common_metrics(bars, i)
        ema = i.ema20 or ZERO
        m.update(
            previous_close=bars[-2].close,
            previous_peak_close=peak,
            pullback_depth_pct=(peak - latest.close) / peak if peak else ZERO,
            ema20_distance_pct=abs(latest.close - ema) / ema if ema else ZERO,
            prior_short_average_volume=p5,
            previous_average_volume=av,
            prior5_volume_ratio=p5 / av if av else ZERO,
            rebound_body_pct=(latest.close - latest.open) / latest.open if latest.open else ZERO,
        )
        rules = {
            "trend": i.sma20 is not None and i.sma60 is not None and i.sma20 > i.sma60,
            "above_sma60": i.sma60 is not None and latest.close > i.sma60,
            "ema20": ema > 0,
            "positive_peak": peak > 0,
            "pullback_depth": self.c.minimum_pullback_depth_pct
            <= m["pullback_depth_pct"]
            <= self.c.maximum_pullback_depth_pct,
            "ema_proximity": m["ema20_distance_pct"] <= self.c.maximum_ema20_distance_pct,
            "sma20_band": i.sma20 is not None and latest.close >= i.sma20 * D(".98"),
            "rebound": latest.close > bars[-2].close,
            "bullish_candle": latest.close >= latest.open,
            "volume_contraction": m["prior5_volume_ratio"] <= self.c.maximum_prior5_volume_ratio,
        }
        score = quantize_score(
            triangular_score(
                m["pullback_depth_pct"],
                self.c.minimum_pullback_depth_pct,
                self.c.ideal_pullback_depth_pct,
                self.c.maximum_pullback_depth_pct,
            )
            * D(".35")
            + low_is_good(m["ema20_distance_pct"], ZERO, self.c.maximum_ema20_distance_pct)
            * D(".30")
            + low_is_good(
                m["prior5_volume_ratio"],
                self.c.best_prior5_volume_ratio,
                self.c.maximum_prior5_volume_ratio,
            )
            * D(".20")
            + high_is_good(m["rebound_body_pct"], ZERO, self.c.maximum_scored_rebound_body_pct)
            * D(".15")
        )
        return _result(SwingSetup.TREND_PULLBACK, bars, m, rules, score)


class VolatilityContractionBreakoutStrategy:
    def __init__(self, config: SwingScreeningConfig = CONFIG):
        self.c = config

    def evaluate(self, bars: Sequence[DailyBar], i: IndicatorSnapshot) -> ScreeningResult:
        required = max(self.c.contraction_range_lookback + 1, self.c.contraction_long_lookback + 2)
        if len(bars) < required:
            return ScreeningResult(
                symbol=bars[-1].symbol if bars else "",
                passed=False,
                reasons=["FAILED: insufficient_history"],
            )
        latest = bars[-1]
        prior20 = bars[-(self.c.contraction_long_lookback + 1) : -1]
        prior10 = bars[-(self.c.contraction_range_lookback + 1) : -1]
        hi = max(x.high for x in prior10)
        lo = min(x.low for x in prior10)
        trs = [
            true_range(bars[n], bars[n - 1].close)
            for n in range(len(bars) - self.c.contraction_long_lookback - 1, len(bars) - 1)
        ]
        tr20 = avg(trs)
        tr5 = avg(trs[-self.c.contraction_short_lookback :])
        v20 = avg([D(x.volume) for x in prior20])
        v5 = avg([D(x.volume) for x in bars[-(self.c.contraction_short_lookback + 1) : -1]])
        m = common_metrics(bars, i)
        m.update(
            previous_range_high=hi,
            previous_range_low=lo,
            contraction_range_pct=(hi - lo) / hi if hi else ZERO,
            prior_short_average_true_range=tr5,
            prior_long_average_true_range=tr20,
            true_range_contraction_ratio=tr5 / tr20 if tr20 else ZERO,
            prior_short_average_volume=v5,
            prior_long_average_volume=v20,
            prior5_volume_ratio=v5 / v20 if v20 else ZERO,
            breakout_volume_ratio=D(latest.volume) / v20 if v20 else ZERO,
        )
        rules = {
            "trend": i.sma20 is not None and i.sma60 is not None and i.sma20 > i.sma60,
            "above_sma20": i.sma20 is not None and latest.close > i.sma20,
            "positive_previous_high": hi > 0,
            "range_contraction": m["contraction_range_pct"] <= self.c.maximum_contraction_range_pct,
            "true_range_contraction": m["true_range_contraction_ratio"]
            <= self.c.maximum_true_range_contraction_ratio,
            "volume_contraction": m["prior5_volume_ratio"]
            <= self.c.contraction_maximum_prior5_volume_ratio,
            "breakout": latest.close >= hi,
            "volume_expansion": m["breakout_volume_ratio"] >= self.c.minimum_breakout_volume_ratio,
            "bullish_candle": latest.close >= latest.open,
        }
        score = quantize_score(
            low_is_good(m["contraction_range_pct"], D(".03"), self.c.maximum_contraction_range_pct)
            * D(".30")
            + low_is_good(
                m["true_range_contraction_ratio"],
                self.c.best_true_range_contraction_ratio,
                self.c.maximum_true_range_contraction_ratio,
            )
            * D(".25")
            + low_is_good(
                m["prior5_volume_ratio"],
                self.c.contraction_best_prior5_volume_ratio,
                self.c.contraction_maximum_prior5_volume_ratio,
            )
            * D(".20")
            + high_is_good(
                m["breakout_volume_ratio"],
                self.c.minimum_breakout_volume_ratio,
                self.c.maximum_scored_breakout_volume_ratio,
            )
            * D(".25")
        )
        return _result(SwingSetup.VOLATILITY_CONTRACTION_BREAKOUT, bars, m, rules, score)


class MultiSetupSwingStrategy:
    def __init__(self, config: SwingScreeningConfig = CONFIG):
        self.c = config
        self.strategies = (
            BoxBreakoutStrategy(config),
            TrendPullbackStrategy(config),
            VolatilityContractionBreakoutStrategy(config),
        )

    def evaluate(self, bars: Sequence[DailyBar], i: IndicatorSnapshot) -> ScreeningResult:
        symbol = bars[-1].symbol if bars else ""
        common = common_metrics(bars, i) if bars and len(bars) >= 20 else {}
        exclusions = []
        if len(bars) < self.c.minimum_history_bars:
            exclusions.append("insufficient_history")
        elif bars[-1].close < self.c.minimum_close:
            exclusions.append("invalid_price")
        elif bars[-1].volume <= 0:
            exclusions.append("zero_volume")
        elif i.sma20 is None or i.sma60 is None or i.atr14 is None:
            exclusions.append("missing_indicator")
        elif common["average_trading_value_20"] < self.c.minimum_average_trading_value_20:
            exclusions.append("insufficient_liquidity")
        elif common["atr_pct"] > self.c.maximum_atr_pct:
            exclusions.append("excessive_volatility")
        if exclusions:
            return ScreeningResult(
                symbol=symbol,
                passed=False,
                reasons=[f"EXCLUDED: {x}" for x in exclusions],
                metrics=common,
                screener_name=self.c.screener_name,
                screener_version=self.c.screener_version,
                configuration_snapshot=self.c.model_dump(),
            )
        results = [s.evaluate(bars, i) for s in self.strategies]
        passed = {x.primary_setup: x for x in results if x.passed and x.primary_setup is not None}
        matched = [x for x in PRIORITY if x in passed]
        scores = {x: passed[x].setup_scores[x] for x in matched}
        primary = min(matched, key=lambda x: (-scores[x], PRIORITY.index(x))) if matched else None
        metrics = dict(common)
        setup_metrics = {}
        rules = {}
        reasons: list[str] = []
        for result in results:
            setup_metrics.update(result.setup_metrics)
            setup = result.evaluated_setup
            if setup is None:
                continue
            rules.update({f"{setup}:{k}": v for k, v in result.rule_evaluations.items()})
            reasons.extend(f"{setup}: {reason}" for reason in result.reasons)
        return ScreeningResult(
            symbol=symbol,
            passed=bool(matched),
            reasons=reasons,
            metrics=metrics,
            matched_setups=matched,
            primary_setup=primary,
            setup_scores=scores,
            screener_name=self.c.screener_name,
            screener_version=self.c.screener_version,
            configuration_snapshot=self.c.model_dump(),
            setup_metrics=setup_metrics,
            rule_evaluations=rules,
        )
