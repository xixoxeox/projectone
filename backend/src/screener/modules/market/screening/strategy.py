"""Contract shared by all screening strategies."""

from collections.abc import Sequence
from typing import Protocol

from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.models import IndicatorSnapshot
from screener.modules.market.screening.models import ScreeningResult


class ScreeningStrategy(Protocol):
    """A pure evaluation of market bars and their calculated indicators."""

    def evaluate(
        self,
        bars: Sequence[DailyBar],
        indicators: IndicatorSnapshot,
    ) -> ScreeningResult: ...
