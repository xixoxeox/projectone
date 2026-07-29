"""Deterministic scoring and ranking of passing screening results."""

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from screener.modules.market.ranking.models import RankedCandidate
from screener.modules.market.screening.models import ScreeningResult

ZERO = Decimal("0")
HUNDRED = Decimal("100")
SCORE_QUANTUM = Decimal("0.01")

TREND_WEIGHT = Decimal("0.30")
BREAKOUT_WEIGHT = Decimal("0.30")
VOLUME_WEIGHT = Decimal("0.25")
VOLATILITY_WEIGHT = Decimal("0.15")

TREND_MAX_RATIO = Decimal("0.20")
BREAKOUT_MAX_RATIO = Decimal("0.10")
VOLUME_MIN_RATIO = Decimal("1.0")
VOLUME_MAX_RATIO = Decimal("3.0")
VOLATILITY_MIN_RATIO = Decimal("0.01")
VOLATILITY_IDEAL_MIN_RATIO = Decimal("0.03")
VOLATILITY_IDEAL_MAX_RATIO = Decimal("0.06")
VOLATILITY_MAX_RATIO = Decimal("0.12")


class CandidateRanker:
    """Assign transparent weighted scores and stable ranks to candidates."""

    def rank(self, results: Sequence[ScreeningResult]) -> list[RankedCandidate]:
        """Validate, score, sort, and rank passing screening results."""
        self._validate_request(results)
        scored = [self._score_candidate(result) for result in results]
        scored.sort(key=lambda candidate: candidate.total_score, reverse=True)
        return [
            candidate.model_copy(update={"rank": rank}) for rank, candidate in enumerate(scored, 1)
        ]

    @staticmethod
    def _validate_request(results: Sequence[ScreeningResult]) -> None:
        seen: set[str] = set()
        for result in results:
            if not result.passed:
                raise ValueError(f"screening result for {result.symbol!r} did not pass")
            if not result.symbol.strip():
                raise ValueError("screening result symbol must not be blank")
            if result.symbol in seen:
                raise ValueError(f"duplicate symbol: {result.symbol}")
            seen.add(result.symbol)

    def _score_candidate(self, result: ScreeningResult) -> RankedCandidate:
        warnings: list[str] = []
        components = {
            "trend": self._score_trend(result.metrics, warnings),
            "breakout": self._score_breakout(result.metrics, warnings),
            "volume": self._score_volume(result.metrics, warnings),
            "volatility": self._score_volatility(result.metrics, warnings),
        }
        total = self._normalize_score(
            components["trend"] * TREND_WEIGHT
            + components["breakout"] * BREAKOUT_WEIGHT
            + components["volume"] * VOLUME_WEIGHT
            + components["volatility"] * VOLATILITY_WEIGHT
        )
        return RankedCandidate(
            symbol=result.symbol,
            rank=1,
            total_score=total,
            component_scores=components,
            source_result=result,
            warnings=warnings,
        )

    def _score_trend(self, metrics: dict[str, Decimal], warnings: list[str]) -> Decimal:
        sma20 = self._metric(metrics, "sma20", "trend", warnings)
        sma60 = self._metric(metrics, "sma60", "trend", warnings)
        if sma20 is None or sma60 is None:
            return self._normalize_score(ZERO)
        if sma60 <= ZERO:
            self._warn(warnings, "trend score unavailable: sma60 must be greater than zero")
            return self._normalize_score(ZERO)
        ratio = (sma20 - sma60) / sma60
        return self._linear_score(ratio, ZERO, TREND_MAX_RATIO)

    def _score_breakout(self, metrics: dict[str, Decimal], warnings: list[str]) -> Decimal:
        close = self._metric(metrics, "close", "breakout", warnings)
        previous_high = self._metric(metrics, "previous_high20", "breakout", warnings)
        if close is None or previous_high is None:
            return self._normalize_score(ZERO)
        if previous_high <= ZERO:
            self._warn(
                warnings,
                "breakout score unavailable: previous_high20 must be greater than zero",
            )
            return self._normalize_score(ZERO)
        ratio = (close - previous_high) / previous_high
        return self._linear_score(ratio, ZERO, BREAKOUT_MAX_RATIO)

    def _score_volume(self, metrics: dict[str, Decimal], warnings: list[str]) -> Decimal:
        volume = self._metric(metrics, "volume", "volume", warnings)
        average = self._metric(metrics, "avg_volume20", "volume", warnings)
        if volume is None or average is None:
            return self._normalize_score(ZERO)
        if volume < ZERO:
            self._warn(warnings, "volume score unavailable: volume must be non-negative")
            return self._normalize_score(ZERO)
        if average <= ZERO:
            self._warn(
                warnings,
                "volume score unavailable: avg_volume20 must be greater than zero",
            )
            return self._normalize_score(ZERO)
        return self._linear_score(volume / average, VOLUME_MIN_RATIO, VOLUME_MAX_RATIO)

    def _score_volatility(self, metrics: dict[str, Decimal], warnings: list[str]) -> Decimal:
        atr14 = self._metric(metrics, "atr14", "volatility", warnings)
        close = self._metric(metrics, "close", "volatility", warnings)
        if atr14 is None or close is None:
            return self._normalize_score(ZERO)
        if close <= ZERO:
            self._warn(warnings, "volatility score unavailable: close must be greater than zero")
            return self._normalize_score(ZERO)
        if atr14 < ZERO:
            self._warn(warnings, "volatility score unavailable: atr14 must be non-negative")
            return self._normalize_score(ZERO)

        ratio = atr14 / close
        if ratio <= VOLATILITY_MIN_RATIO or ratio >= VOLATILITY_MAX_RATIO:
            return self._normalize_score(ZERO)
        if ratio < VOLATILITY_IDEAL_MIN_RATIO:
            return self._linear_score(ratio, VOLATILITY_MIN_RATIO, VOLATILITY_IDEAL_MIN_RATIO)
        if ratio <= VOLATILITY_IDEAL_MAX_RATIO:
            return self._normalize_score(HUNDRED)
        score = (
            (VOLATILITY_MAX_RATIO - ratio)
            / (VOLATILITY_MAX_RATIO - VOLATILITY_IDEAL_MAX_RATIO)
            * HUNDRED
        )
        return self._normalize_score(score)

    def _linear_score(self, value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
        if value <= minimum:
            return self._normalize_score(ZERO)
        if value >= maximum:
            return self._normalize_score(HUNDRED)
        return self._normalize_score((value - minimum) / (maximum - minimum) * HUNDRED)

    @staticmethod
    def _metric(
        metrics: dict[str, Decimal],
        name: str,
        component: str,
        warnings: list[str],
    ) -> Decimal | None:
        value = metrics.get(name)
        if value is None:
            CandidateRanker._warn(warnings, f"{component} score unavailable: missing {name}")
            return None
        if not value.is_finite():
            CandidateRanker._warn(warnings, f"{component} score unavailable: invalid {name}")
            return None
        return value

    @staticmethod
    def _warn(warnings: list[str], warning: str) -> None:
        if warning not in warnings:
            warnings.append(warning)

    @staticmethod
    def _normalize_score(score: Decimal) -> Decimal:
        bounded = min(HUNDRED, max(ZERO, score))
        return bounded.quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)


__all__ = ["CandidateRanker"]


class SwingCandidateRanker:
    """Deterministic v2 ranking for aggregated multi-setup candidates."""

    _priority = {"volatility_contraction_breakout": 0, "box_breakout": 1, "trend_pullback": 2}

    def __init__(self, minimum_liquidity: Decimal = Decimal("1000000000")) -> None:
        self.minimum_liquidity = minimum_liquidity

    def rank(self, results: Sequence[ScreeningResult]) -> list[RankedCandidate]:
        CandidateRanker._validate_request(results)
        candidates = [self._score(result) for result in results]
        candidates.sort(
            key=lambda c: (
                -c.total_score,
                -c.source_result.setup_scores.get(c.source_result.primary_setup or "", ZERO),
                self._priority.get(c.source_result.primary_setup or "", 99),
                c.symbol,
            )
        )
        return [
            candidate.model_copy(update={"rank": rank})
            for rank, candidate in enumerate(candidates, 1)
        ]

    def _score(self, result: ScreeningResult) -> RankedCandidate:
        metrics = result.metrics
        sma20 = metrics.get("sma20", ZERO)
        sma60 = metrics.get("sma60", ZERO)
        trend = self._linear((sma20 - sma60) / sma60 if sma60 > 0 else ZERO, ZERO, Decimal(".20"))
        setup = max(result.setup_scores.values(), default=ZERO)
        liquidity = self._linear(
            metrics.get("average_trading_value_20", ZERO) / self.minimum_liquidity,
            Decimal("1"),
            Decimal("5"),
        )
        atr = metrics.get("atr_pct", ZERO)
        volatility = CandidateRanker()._score_volatility({"atr14": atr, "close": Decimal("1")}, [])
        components = {
            "trend": trend,
            "setup": setup,
            "liquidity": liquidity,
            "volatility": volatility,
        }
        total = CandidateRanker._normalize_score(
            trend * Decimal(".25")
            + setup * Decimal(".45")
            + liquidity * Decimal(".15")
            + volatility * Decimal(".15")
        )
        return RankedCandidate(
            symbol=result.symbol,
            rank=1,
            total_score=total,
            component_scores=components,
            source_result=result,
            warnings=result.warnings,
        )

    @staticmethod
    def _linear(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
        return CandidateRanker()._linear_score(value, minimum, maximum)


__all__ = ["CandidateRanker", "SwingCandidateRanker"]
