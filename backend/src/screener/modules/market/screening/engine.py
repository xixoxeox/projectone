"""Strategy-agnostic screening orchestration."""

from collections.abc import Sequence

from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.models import IndicatorSnapshot
from screener.modules.market.screening.models import ScreeningResult
from screener.modules.market.screening.strategy import ScreeningStrategy


class ScreeningEngine:
    """Execute a selected strategy against the bars for one symbol."""

    def __init__(self, strategy: ScreeningStrategy) -> None:
        self._strategy = strategy

    def evaluate(
        self,
        bars: Sequence[DailyBar],
        indicators: IndicatorSnapshot,
    ) -> ScreeningResult:
        """Delegate evaluation without adding data-source or persistence concerns."""
        return self._strategy.evaluate(bars, indicators)
