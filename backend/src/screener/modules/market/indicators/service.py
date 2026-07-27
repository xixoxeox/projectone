"""Application-facing technical indicator service."""

from collections.abc import Sequence

from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.calculations import (
    average_true_range,
    average_volume,
    exponential_moving_average,
    highest_high,
    lowest_low,
    simple_moving_average,
)
from screener.modules.market.indicators.models import IndicatorSnapshot


class IndicatorService:
    """Calculate the latest reusable indicator snapshot from chronological bars."""

    def calculate(self, bars: Sequence[DailyBar]) -> IndicatorSnapshot:
        if any(
            left.trading_date >= right.trading_date
            for left, right in zip(bars, bars[1:], strict=False)
        ):
            raise ValueError("bars must be ordered by unique ascending trading date")

        closes = [bar.close for bar in bars]
        return IndicatorSnapshot(
            sma5=simple_moving_average(closes, 5),
            sma20=simple_moving_average(closes, 20),
            sma60=simple_moving_average(closes, 60),
            sma120=simple_moving_average(closes, 120),
            ema20=exponential_moving_average(closes, 20),
            atr14=average_true_range(bars, 14),
            avg_volume20=average_volume(bars, 20),
            highest20=highest_high(bars, 20),
            lowest20=lowest_low(bars, 20),
            highest60=highest_high(bars, 60),
            lowest60=lowest_low(bars, 60),
        )
