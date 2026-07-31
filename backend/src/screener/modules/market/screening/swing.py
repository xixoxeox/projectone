"""Deterministic, Decimal-only multi-setup swing screening."""

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise

from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.models import IndicatorSnapshot, ScreeningResult

ZERO, HUNDRED = Decimal("0"), Decimal("100")
type Evaluation = tuple[bool, dict[str, Decimal], dict[str, bool]]
type CommonEvaluation = tuple[bool, list[str], dict[str, Decimal]]
SETUP_ORDER = ("volatility_contraction_breakout", "box_breakout", "trend_pullback")


def _true_ranges(bars: Sequence[DailyBar]) -> list[Decimal]:
    return [
        max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        for previous, current in pairwise(bars)
    ]


def _finite(*values: Decimal) -> None:
    if any(not value.is_finite() for value in values):
        raise ValueError("scores require finite Decimal values")


def clamp_score(value: Decimal) -> Decimal:
    _finite(value)
    return min(HUNDRED, max(ZERO, value))


def quantize_score(value: Decimal) -> Decimal:
    return clamp_score(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def high_is_good(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    _finite(value, minimum, maximum)
    if maximum <= minimum:
        raise ValueError("maximum must exceed minimum")
    return quantize_score((value - minimum) / (maximum - minimum) * HUNDRED)


def low_is_good(value: Decimal, best: Decimal, worst: Decimal) -> Decimal:
    _finite(value, best, worst)
    if worst <= best:
        raise ValueError("worst must exceed best")
    return quantize_score((worst - value) / (worst - best) * HUNDRED)


def triangular_score(value: Decimal, minimum: Decimal, ideal: Decimal, maximum: Decimal) -> Decimal:
    _finite(value, minimum, ideal, maximum)
    if not minimum < ideal < maximum:
        raise ValueError("minimum < ideal < maximum is required")
    return (
        high_is_good(value, minimum, ideal)
        if value <= ideal
        else low_is_good(value, ideal, maximum)
    )


@dataclass(frozen=True)
class SwingScreeningConfig:
    screener_name: str = "multi_setup_swing"
    screener_version: str = "1"
    minimum_history_bars: int = 61
    minimum_close: Decimal = Decimal("1000")
    minimum_average_trading_value_20: Decimal = Decimal("1000000000")
    maximum_atr_pct: Decimal = Decimal("0.12")
    minimum_candidate_score: Decimal = Decimal("80")
    maximum_candidates: int = 5
    box_lookback: int = 20
    maximum_box_width_pct: Decimal = Decimal("0.15")
    minimum_breakout_volume_ratio: Decimal = Decimal("1.20")
    maximum_scored_breakout_pct: Decimal = Decimal("0.05")
    maximum_scored_volume_ratio: Decimal = Decimal("3.00")
    pullback_lookback: int = 20
    pullback_volume_lookback: int = 5
    minimum_pullback_depth_pct: Decimal = Decimal("0.03")
    ideal_pullback_depth_pct: Decimal = Decimal("0.06")
    maximum_pullback_depth_pct: Decimal = Decimal("0.12")
    maximum_ema20_distance_pct: Decimal = Decimal("0.04")
    maximum_prior_short_volume_ratio: Decimal = Decimal("0.90")
    best_prior_short_volume_ratio: Decimal = Decimal("0.50")
    maximum_scored_rebound_body_pct: Decimal = Decimal("0.03")
    contraction_range_lookback: int = 10
    contraction_short_lookback: int = 5
    contraction_long_lookback: int = 20
    maximum_contraction_range_pct: Decimal = Decimal("0.08")
    maximum_true_range_contraction_ratio: Decimal = Decimal("0.70")
    best_true_range_contraction_ratio: Decimal = Decimal("0.40")
    contraction_maximum_prior_short_volume_ratio: Decimal = Decimal("0.80")
    contraction_best_prior_short_volume_ratio: Decimal = Decimal("0.50")
    maximum_scored_breakout_volume_ratio: Decimal = Decimal("3.00")

    def __post_init__(self) -> None:
        looks = [
            self.box_lookback,
            self.pullback_lookback,
            self.pullback_volume_lookback,
            self.contraction_range_lookback,
            self.contraction_short_lookback,
            self.contraction_long_lookback,
        ]
        if any(value <= 0 for value in looks):
            raise ValueError("lookbacks must be positive")
        if self.pullback_volume_lookback > self.pullback_lookback:
            raise ValueError("invalid pullback lookback")
        if self.contraction_short_lookback > self.contraction_long_lookback:
            raise ValueError("invalid contraction lookback")
        required = max(
            20,
            self.box_lookback + 1,
            self.pullback_lookback + 1,
            self.pullback_volume_lookback + 1,
            self.contraction_range_lookback + 1,
            self.contraction_long_lookback + 2,
        )
        if self.minimum_history_bars < required:
            raise ValueError("minimum_history_bars is unsafe")
        if not ZERO <= self.minimum_candidate_score <= HUNDRED:
            raise ValueError("minimum_candidate_score must be between 0 and 100")
        if self.maximum_candidates <= 0:
            raise ValueError("maximum_candidates must be positive")

    def snapshot(self) -> dict[str, str | int]:
        return {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in asdict(self).items()
        }


class MultiSetupSwingStrategy:
    def __init__(self, config: SwingScreeningConfig | None = None) -> None:
        self.config = config or SwingScreeningConfig()

    def evaluate(self, bars: Sequence[DailyBar], indicators: IndicatorSnapshot) -> ScreeningResult:
        symbol = bars[-1].symbol if bars else ""
        common = self._common(bars, indicators)
        methods: tuple[
            tuple[str, Callable[[Sequence[DailyBar], IndicatorSnapshot], Evaluation]], ...
        ] = (
            ("box_breakout", self._box),
            ("trend_pullback", self._pullback),
            ("volatility_contraction_breakout", self._contraction),
        )
        evaluations = {name: method(bars, indicators) for name, method in methods}
        rules = {
            f"{name}:{key}": value
            for name, (_, _, rs) in evaluations.items()
            for key, value in rs.items()
        }
        matched = [name for name in SETUP_ORDER if evaluations[name][0] and common[0]]
        evaluated_scores = {name: evaluations[name][1].pop("setup_score") for name in SETUP_ORDER}
        scores = {name: evaluated_scores[name] for name in matched}
        primary = (
            min(matched, key=lambda name: (-scores[name], SETUP_ORDER.index(name)))
            if matched
            else None
        )
        return ScreeningResult(
            symbol=symbol,
            passed=bool(matched),
            reasons=common[1],
            metrics=common[2],
            matched_setups=matched,
            primary_setup=primary,
            setup_scores=scores,
            setup_metrics={name: value[1] for name, value in evaluations.items()},
            rule_evaluations=rules,
            screener_name=self.config.screener_name,
            screener_version=self.config.screener_version,
            configuration_snapshot=self.config.snapshot(),
        )

    def _common(self, bars: Sequence[DailyBar], i: IndicatorSnapshot) -> CommonEvaluation:
        if not bars:
            return False, ["missing_target_bar"], {}
        latest = bars[-1]
        avg = (
            sum((b.close * Decimal(b.volume) for b in bars[-20:]), ZERO) / Decimal(20)
            if len(bars) >= 20
            else ZERO
        )
        atr_pct = i.atr14 / latest.close if i.atr14 is not None and latest.close > 0 else ZERO
        rules = [
            len(bars) >= self.config.minimum_history_bars,
            latest.close >= self.config.minimum_close,
            latest.volume > 0,
            i.sma20 is not None and i.sma60 is not None and i.atr14 is not None,
            avg >= self.config.minimum_average_trading_value_20,
            atr_pct <= self.config.maximum_atr_pct,
        ]
        names = [
            "insufficient_history",
            "invalid_price",
            "zero_volume",
            "missing_indicator",
            "insufficient_liquidity",
            "excessive_volatility",
        ]
        metrics = {
            "close": latest.close,
            "latest_close": latest.close,
            "average_trading_value_20": avg,
            "atr_pct": atr_pct,
        }
        for key, val in (
            ("sma20", i.sma20),
            ("sma60", i.sma60),
            ("ema20", i.ema20),
            ("atr14", i.atr14),
        ):
            if val is not None:
                metrics[key] = val
        return (
            all(rules),
            [name for name, passed in zip(names, rules, strict=True) if not passed],
            metrics,
        )

    def _box(self, bars: Sequence[DailyBar], i: IndicatorSnapshot) -> Evaluation:
        c = self.config
        latest = bars[-1] if bars else None
        prior = bars[-c.box_lookback - 1 : -1]
        if latest is None or len(prior) < c.box_lookback:
            return False, {"setup_score": ZERO}, {}
        hi = max(b.high for b in prior)
        lo = min(b.low for b in prior)
        av = sum((Decimal(b.volume) for b in prior), ZERO) / Decimal(len(prior))
        width = (hi - lo) / hi if hi else ZERO
        breakout = (latest.close - hi) / hi if hi else ZERO
        vr = Decimal(latest.volume) / av if av else ZERO
        rules = {
            "trend": i.sma20 is not None and i.sma60 is not None and i.sma20 > i.sma60,
            "above_sma20": i.sma20 is not None and latest.close > i.sma20,
            "box_width": hi > 0 and width <= c.maximum_box_width_pct,
            "breakout": latest.close >= hi,
            "volume": vr >= c.minimum_breakout_volume_ratio,
            "bullish": latest.close >= latest.open,
        }
        score = quantize_score(
            low_is_good(width, Decimal(".05"), c.maximum_box_width_pct) * Decimal(".35")
            + high_is_good(breakout, ZERO, c.maximum_scored_breakout_pct) * Decimal(".30")
            + high_is_good(vr, c.minimum_breakout_volume_ratio, c.maximum_scored_volume_ratio)
            * Decimal(".35")
        )
        return (
            all(rules.values()),
            {
                "previous_box_high": hi,
                "previous_box_low": lo,
                "box_width_pct": width,
                "breakout_pct": breakout,
                "previous_average_volume": av,
                "volume_ratio": vr,
                "setup_score": score,
            },
            rules,
        )

    def _pullback(self, bars: Sequence[DailyBar], i: IndicatorSnapshot) -> Evaluation:
        c = self.config
        latest = bars[-1] if bars else None
        prior = bars[-c.pullback_lookback - 1 : -1]
        if latest is None or len(prior) < c.pullback_lookback:
            return False, {"setup_score": ZERO}, {}
        peak = max(b.close for b in prior)
        depth = (peak - latest.close) / peak if peak else ZERO
        ema = i.ema20 or ZERO
        dist = abs(latest.close - ema) / ema if ema > 0 else ZERO
        av = sum((Decimal(b.volume) for b in prior), ZERO) / Decimal(len(prior))
        short = sum(
            (Decimal(b.volume) for b in prior[-c.pullback_volume_lookback :]), ZERO
        ) / Decimal(c.pullback_volume_lookback)
        vr = short / av if av else ZERO
        body = (latest.close - latest.open) / latest.open if latest.open else ZERO
        rules = {
            "trend": i.sma20 is not None and i.sma60 is not None and i.sma20 > i.sma60,
            "above_sma60": i.sma60 is not None and latest.close > i.sma60,
            "ema20": ema > 0,
            "depth": c.minimum_pullback_depth_pct <= depth <= c.maximum_pullback_depth_pct,
            "ema_distance": dist <= c.maximum_ema20_distance_pct,
            "sma20_band": i.sma20 is not None and latest.close >= i.sma20 * Decimal(".98"),
            "rebound": latest.close > bars[-2].close,
            "bullish": latest.close >= latest.open,
            "volume": vr <= c.maximum_prior_short_volume_ratio,
        }
        score = quantize_score(
            triangular_score(
                depth,
                c.minimum_pullback_depth_pct,
                c.ideal_pullback_depth_pct,
                c.maximum_pullback_depth_pct,
            )
            * Decimal(".35")
            + low_is_good(dist, ZERO, c.maximum_ema20_distance_pct) * Decimal(".30")
            + low_is_good(vr, c.best_prior_short_volume_ratio, c.maximum_prior_short_volume_ratio)
            * Decimal(".20")
            + high_is_good(body, ZERO, c.maximum_scored_rebound_body_pct) * Decimal(".15")
        )
        return (
            all(rules.values()),
            {
                "previous_peak_close": peak,
                "pullback_depth_pct": depth,
                "ema20_distance_pct": dist,
                "prior_short_average_volume": short,
                "previous_average_volume": av,
                "prior_short_volume_ratio": vr,
                "rebound_body_pct": body,
                "setup_score": score,
            },
            rules,
        )

    def _contraction(self, bars: Sequence[DailyBar], i: IndicatorSnapshot) -> Evaluation:
        c = self.config
        latest = bars[-1] if bars else None
        prior = bars[-c.contraction_long_lookback - 1 : -1]
        if (
            latest is None
            or len(prior) < c.contraction_long_lookback
            or len(bars) < c.contraction_long_lookback + 2
        ):
            return False, {"setup_score": ZERO}, {}
        rng = prior[-c.contraction_range_lookback :]
        hi = max(b.high for b in rng)
        lo = min(b.low for b in rng)
        rp = (hi - lo) / hi if hi else ZERO
        seq = bars[-c.contraction_long_lookback - 2 : -1]
        trs = _true_ranges(seq)
        longtr = sum(trs, ZERO) / Decimal(len(trs))
        shorttr = sum(trs[-c.contraction_short_lookback :], ZERO) / Decimal(
            c.contraction_short_lookback
        )
        trr = shorttr / longtr if longtr else ZERO
        lv = sum((Decimal(b.volume) for b in prior), ZERO) / Decimal(len(prior))
        sv = sum(
            (Decimal(b.volume) for b in prior[-c.contraction_short_lookback :]), ZERO
        ) / Decimal(c.contraction_short_lookback)
        svr = sv / lv if lv else ZERO
        bvr = Decimal(latest.volume) / lv if lv else ZERO
        rules = {
            "trend": i.sma20 is not None and i.sma60 is not None and i.sma20 > i.sma60,
            "above_sma20": i.sma20 is not None and latest.close > i.sma20,
            "range": hi > 0 and rp <= c.maximum_contraction_range_pct,
            "true_range": longtr > 0 and trr <= c.maximum_true_range_contraction_ratio,
            "volume_contraction": lv > 0 and svr <= c.contraction_maximum_prior_short_volume_ratio,
            "breakout": latest.close >= hi,
            "breakout_volume": bvr >= c.minimum_breakout_volume_ratio,
            "bullish": latest.close >= latest.open,
        }
        score = quantize_score(
            low_is_good(rp, Decimal(".03"), c.maximum_contraction_range_pct) * Decimal(".30")
            + low_is_good(
                trr, c.best_true_range_contraction_ratio, c.maximum_true_range_contraction_ratio
            )
            * Decimal(".25")
            + low_is_good(
                svr,
                c.contraction_best_prior_short_volume_ratio,
                c.contraction_maximum_prior_short_volume_ratio,
            )
            * Decimal(".20")
            + high_is_good(
                bvr, c.minimum_breakout_volume_ratio, c.maximum_scored_breakout_volume_ratio
            )
            * Decimal(".25")
        )
        return (
            all(rules.values()),
            {
                "previous_range_high": hi,
                "previous_range_low": lo,
                "contraction_range_pct": rp,
                "prior_long_average_true_range": longtr,
                "prior_short_average_true_range": shorttr,
                "true_range_contraction_ratio": trr,
                "prior_long_average_volume": lv,
                "prior_short_average_volume": sv,
                "prior_short_volume_ratio": svr,
                "breakout_volume_ratio": bvr,
                "setup_score": score,
            },
            rules,
        )
