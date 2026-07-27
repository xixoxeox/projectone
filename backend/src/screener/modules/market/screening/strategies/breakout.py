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
        symbol = latest.symbol if latest is not None else ""
        reasons: list[str] = []
        outcomes: list[bool] = []
        metrics = self._metrics(latest, indicators)

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
            "latest close >= Highest20",
            latest.close if latest is not None else None,
            indicators.highest20,
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
    ) -> dict[str, Decimal]:
        metrics: dict[str, Decimal] = {}
        if latest is not None:
            metrics["close"] = latest.close
            metrics["volume"] = Decimal(latest.volume)
        for name, value in (
            ("sma20", indicators.sma20),
            ("sma60", indicators.sma60),
            ("highest20", indicators.highest20),
            ("avg_volume20", indicators.avg_volume20),
        ):
            if value is not None:
                metrics[name] = value
        return metrics


class Comparison(Protocol):
    def __call__(self, left: Decimal, right: Decimal) -> bool: ...
