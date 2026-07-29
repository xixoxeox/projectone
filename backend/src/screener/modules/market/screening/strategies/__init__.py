"""Built-in screening strategies."""

from screener.modules.market.screening.strategies.breakout import BreakoutStrategy
from screener.modules.market.screening.swing import (
    BoxBreakoutStrategy,
    MultiSetupSwingStrategy,
    TrendPullbackStrategy,
    VolatilityContractionBreakoutStrategy,
)

__all__ = [
    "BoxBreakoutStrategy",
    "BreakoutStrategy",
    "MultiSetupSwingStrategy",
    "TrendPullbackStrategy",
    "VolatilityContractionBreakoutStrategy",
]
