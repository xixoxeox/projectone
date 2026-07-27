"""Trend, price breakout, and volume confirmation strategy."""

from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.models import IndicatorSnapshot
from screener.modules.market.screening.models import ScreeningResult


class BreakoutStrategy:
    """Identify a 20-period high in an established, volume-backed uptrend."""

    def evaluate(
        self,
        bars: Sequence[DailyBar],
        indicators: IndicatorSnapshot,
    ) -> ScreeningResult:
        latest = bars[-1] if bars else None
        previous_high20 = max(bar.high for bar in bars[-21:-1]) if len(bars) >= 21 else None
        symbol = latest.symbol if latest is not None else ""
        reasons: list[str] = []
        outcomes: list[bool] = []
        metrics = self._metrics(latest, indicators, previous_high20)

        self._compare(
            reasons,
            outcomes,
            "SMA20 > SMA60",
            indicators.sma20,
            indicators.sma60,
            lambda left, right: left > right,
        )
        self._compare(
            reasons,
            outcomes,
            "latest close > SMA20",
            latest.close if latest is not None else None,
            indicators.sma20,
            lambda left, right: left > right,
        )
        self._compare(
            reasons,
            outcomes,
            "latest close >= previous High20",
            latest.close if latest is not None else None,
            previous_high20,
            lambda left, right: left >= right,
        )
        self._compare(
            reasons,
            outcomes,
            "latest volume > AverageVolume20",
            Decimal(latest.volume) if latest is not None else None,
            indicators.avg_volume20,
            lambda left, right: left > right,
        )

        warnings = ["No bars supplied."] if latest is None else []
        return ScreeningResult(
            symbol=symbol,
            passed=all(outcomes),
            reasons=reasons,
            warnings=warnings,
            metrics=metrics,
        )

    @staticmethod
    def _compare(
        reasons: list[str],
        outcomes: list[bool],
        rule: str,
        left: Decimal | None,
        right: Decimal | None,
        comparison: "Comparison",
    ) -> None:
        if left is None or right is None:
            outcomes.append(False)
            reasons.append(f"FAILED: {rule} (insufficient history)")
            return

        passed = comparison(left, right)
        outcomes.append(passed)
        status = "PASSED" if passed else "FAILED"
        reasons.append(f"{status}: {rule} ({left} vs {right})")

    @staticmethod
    def _metrics(
        latest: DailyBar | None,
        indicators: IndicatorSnapshot,
        previous_high20: Decimal | None,
    ) -> dict[str, Decimal]:
        metrics: dict[str, Decimal] = {}
        if latest is not None:
            metrics["close"] = latest.close
            metrics["volume"] = Decimal(latest.volume)
        if previous_high20 is not None:
            metrics["previous_high20"] = previous_high20
        for name, value in (
            ("sma20", indicators.sma20),
            ("sma60", indicators.sma60),
            ("avg_volume20", indicators.avg_volume20),
            ("atr14", indicators.atr14),
        ):
            if value is not None:
                metrics[name] = value
        return metrics


class Comparison(Protocol):
    def __call__(self, left: Decimal, right: Decimal) -> bool: ...
