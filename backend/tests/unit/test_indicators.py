from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.calculations import (
    average_true_range,
    average_volume,
    exponential_moving_average,
    highest_high,
    lowest_low,
    simple_moving_average,
)
from screener.modules.market.indicators.service import IndicatorService


def make_bars(count: int) -> list[DailyBar]:
    start = date(2025, 1, 1)
    return [
        DailyBar(
            symbol="TEST",
            trading_date=start + timedelta(days=index),
            open=Decimal(index + 1),
            high=Decimal(index + 3),
            low=Decimal(index),
            close=Decimal(index + 1),
            volume=(index + 1) * 100,
            source="test",
            as_of=datetime(2025, 1, 1, tzinfo=UTC),
        )
        for index in range(count)
    ]


def test_simple_moving_average_uses_latest_window() -> None:
    values = [Decimal(value) for value in range(1, 8)]
    assert simple_moving_average(values, 5) == Decimal(5)


def test_exponential_moving_average_is_seeded_by_sma() -> None:
    values = [Decimal(value) for value in range(1, 22)]
    expected = (Decimal(21) - Decimal("10.5")) * (Decimal(2) / Decimal(21)) + Decimal("10.5")
    assert exponential_moving_average(values, 20) == expected


def test_average_true_range_accounts_for_previous_close_gaps() -> None:
    bars = make_bars(14)
    bars[13] = bars[13].model_copy(
        update={"open": Decimal(30), "high": Decimal(31), "low": Decimal(29), "close": Decimal(30)}
    )
    # Thirteen ranges of 3 and a final gap true range of 18 (31 - prior close 13).
    assert average_true_range(bars, 14) == Decimal(57) / Decimal(14)


def test_average_volume_uses_latest_window() -> None:
    assert average_volume(make_bars(21), 20) == Decimal(1150)


def test_highest_and_lowest_use_latest_windows() -> None:
    bars = make_bars(21)
    assert highest_high(bars, 20) == Decimal(23)
    assert lowest_low(bars, 20) == Decimal(1)


def test_service_calculates_all_supported_indicators() -> None:
    snapshot = IndicatorService().calculate(make_bars(120))
    assert snapshot.sma5 == Decimal(118)
    assert snapshot.sma20 == Decimal("110.5")
    assert snapshot.sma60 == Decimal("90.5")
    assert snapshot.sma120 == Decimal("60.5")
    assert snapshot.ema20 is not None
    assert snapshot.atr14 == Decimal(3)
    assert snapshot.avg_volume20 == Decimal(11050)
    assert snapshot.highest20 == Decimal(122)
    assert snapshot.lowest20 == Decimal(100)
    assert snapshot.highest60 == Decimal(122)
    assert snapshot.lowest60 == Decimal(60)


def test_insufficient_history_returns_none_per_indicator() -> None:
    snapshot = IndicatorService().calculate(make_bars(19))
    assert snapshot.sma5 == Decimal(17)
    assert snapshot.atr14 == Decimal(3)
    assert snapshot.sma20 is None
    assert snapshot.ema20 is None
    assert snapshot.avg_volume20 is None
    assert snapshot.highest20 is None
    assert snapshot.lowest60 is None


def test_empty_input_returns_empty_snapshot() -> None:
    snapshot = IndicatorService().calculate([])
    assert all(value is None for value in snapshot.model_dump().values())


def test_service_rejects_unordered_or_duplicate_bars() -> None:
    bars = make_bars(2)
    with pytest.raises(ValueError, match="ordered"):
        IndicatorService().calculate(list(reversed(bars)))
    with pytest.raises(ValueError, match="ordered"):
        IndicatorService().calculate([bars[0], bars[0]])


@pytest.mark.parametrize(
    "calculation",
    [
        lambda: simple_moving_average([], 0),
        lambda: exponential_moving_average([], 0),
        lambda: average_true_range([], 0),
        lambda: highest_high([], 0),
        lambda: lowest_low([], 0),
    ],
)
def test_period_must_be_positive(calculation: object) -> None:
    assert callable(calculation)
    with pytest.raises(ValueError, match="positive"):
        calculation()
