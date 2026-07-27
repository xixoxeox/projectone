"""Pure-Python calculations used by the indicator service."""

from collections.abc import Sequence
from decimal import Decimal

from screener.modules.market.domain import DailyBar


def simple_moving_average(values: Sequence[Decimal], period: int) -> Decimal | None:
    """Return the average of the latest ``period`` values."""
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window, start=Decimal(0)) / Decimal(period)


def exponential_moving_average(values: Sequence[Decimal], period: int) -> Decimal | None:
    """Return an EMA seeded with the SMA of the first complete window."""
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        return None
    ema = sum(values[:period], start=Decimal(0)) / Decimal(period)
    multiplier = Decimal(2) / Decimal(period + 1)
    for value in values[period:]:
        ema = (value - ema) * multiplier + ema
    return ema


def average_true_range(bars: Sequence[DailyBar], period: int) -> Decimal | None:
    """Return the simple average of the latest true ranges.

    The first bar's true range is its high-low range when it belongs to the window.
    """
    if period <= 0:
        raise ValueError("period must be positive")
    if len(bars) < period:
        return None
    true_ranges: list[Decimal] = []
    for index, bar in enumerate(bars):
        if index == 0:
            true_ranges.append(bar.high - bar.low)
            continue
        previous_close = bars[index - 1].close
        true_ranges.append(
            max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close))
        )
    return simple_moving_average(true_ranges, period)


def average_volume(bars: Sequence[DailyBar], period: int) -> Decimal | None:
    """Return average volume over the latest complete window."""
    return simple_moving_average([Decimal(bar.volume) for bar in bars], period)


def highest_high(bars: Sequence[DailyBar], period: int) -> Decimal | None:
    """Return the highest high over the latest complete window."""
    if period <= 0:
        raise ValueError("period must be positive")
    if len(bars) < period:
        return None
    return max(bar.high for bar in bars[-period:])


def lowest_low(bars: Sequence[DailyBar], period: int) -> Decimal | None:
    """Return the lowest low over the latest complete window."""
    if period <= 0:
        raise ValueError("period must be positive")
    if len(bars) < period:
        return None
    return min(bar.low for bar in bars[-period:])
