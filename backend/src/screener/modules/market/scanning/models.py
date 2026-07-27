"""Input models for scanning a batch of market symbols."""

from collections.abc import Sequence
from dataclasses import dataclass

from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.models import IndicatorSnapshot


@dataclass(frozen=True, slots=True)
class ScanInput:
    """Caller-supplied data needed to screen one symbol."""

    symbol: str
    bars: Sequence[DailyBar]
    indicators: IndicatorSnapshot
