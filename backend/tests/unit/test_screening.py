from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.models import IndicatorSnapshot
from screener.modules.market.screening.engine import ScreeningEngine
from screener.modules.market.screening.models import ScreeningResult
from screener.modules.market.screening.strategies.breakout import BreakoutStrategy


def bar(
    day: int,
    *,
    high: str,
    close: str,
    volume: int = 2_000,
) -> DailyBar:
    closing_price = Decimal(close)
    high_price = Decimal(high)
    return DailyBar(
        symbol="TEST",
        trading_date=date(2026, 7, 1) + timedelta(days=day),
        open=closing_price - 1,
        high=high_price,
        low=closing_price - 2,
        close=closing_price,
        volume=volume,
        source="test",
        as_of=datetime(2026, 7, 1, tzinfo=UTC) + timedelta(days=day),
    )


def previous_bars(count: int = 20) -> list[DailyBar]:
    return [bar(day, high=str(101 + day), close=str(100 + day)) for day in range(count)]


def bars_with_latest(
    *, high: str = "125", close: str = "122", volume: int = 2_000
) -> list[DailyBar]:
    return [*previous_bars(), bar(20, high=high, close=close, volume=volume)]


def indicators(**updates: Decimal | None) -> IndicatorSnapshot:
    values: dict[str, Decimal | None] = {
        "sma20": Decimal("110"),
        "sma60": Decimal("100"),
        "highest20": Decimal("125"),
        "avg_volume20": Decimal("1000"),
    }
    values.update(updates)
    return IndicatorSnapshot.model_validate(values)


def evaluate(
    bars: list[DailyBar] | None = None,
    snapshot: IndicatorSnapshot | None = None,
) -> ScreeningResult:
    return BreakoutStrategy().evaluate(
        bars if bars is not None else bars_with_latest(), snapshot or indicators()
    )


def test_successful_breakout_uses_previous_twenty_bars() -> None:
    result = evaluate()

    assert result.passed is True
    assert result.metrics["previous_high20"] == Decimal("120")
    assert "highest20" not in result.metrics
    assert result.reasons[2] == "PASSED: latest close >= previous High20 (122 vs 120)"
    assert all(reason.startswith("PASSED:") for reason in result.reasons)


def test_breakout_fails_below_previous_high() -> None:
    result = evaluate(bars_with_latest(high="125", close="119"))

    assert result.passed is False
    assert result.reasons[2] == "FAILED: latest close >= previous High20 (119 vs 120)"


def test_breakout_passes_at_exact_previous_high() -> None:
    result = evaluate(bars_with_latest(high="125", close="120"))

    assert result.passed is True
    assert result.reasons[2] == "PASSED: latest close >= previous High20 (120 vs 120)"


def test_latest_bar_high_is_excluded_from_reference_window() -> None:
    result = evaluate(bars_with_latest(high="130", close="121"))

    assert result.metrics["previous_high20"] == Decimal("120")
    assert result.passed is True


def test_twenty_or_fewer_bars_report_insufficient_breakout_history() -> None:
    result = evaluate(previous_bars())

    assert result.passed is False
    assert "previous_high20" not in result.metrics
    assert result.reasons[2] == ("FAILED: latest close >= previous High20 (insufficient history)")


def test_empty_bars_fail_without_an_exception_and_keep_warning() -> None:
    result = evaluate([])

    assert result.passed is False
    assert result.warnings == ["No bars supplied."]
    assert result.reasons[2].endswith("(insufficient history)")


def test_insufficient_volume_fails_volume_rule() -> None:
    result = evaluate(bars_with_latest(volume=1_000))

    assert result.passed is False
    assert result.reasons[-1] == "FAILED: latest volume > AverageVolume20 (1000 vs 1000)"


def test_sma20_not_above_sma60_fails_trend_rule() -> None:
    result = evaluate(snapshot=indicators(sma20=Decimal("110"), sma60=Decimal("110")))

    assert result.passed is False
    assert result.reasons[0] == "FAILED: SMA20 > SMA60 (110 vs 110)"


def test_latest_close_not_above_sma20_fails_price_rule() -> None:
    result = evaluate(
        bars_with_latest(high="125", close="110"),
        indicators(sma20=Decimal("110")),
    )

    assert result.passed is False
    assert result.reasons[1] == "FAILED: latest close > SMA20 (110 vs 110)"


def test_missing_indicators_fail_their_rules() -> None:
    result = evaluate(snapshot=indicators(sma20=None, sma60=None, avg_volume20=None))

    assert result.passed is False
    assert result.reasons[0].endswith("(insufficient history)")
    assert result.reasons[1].endswith("(insufficient history)")
    assert result.reasons[3].endswith("(insufficient history)")


def test_screening_engine_delegates_to_strategy() -> None:
    class StubStrategy:
        def __init__(self) -> None:
            self.called_with: tuple[Sequence[DailyBar], IndicatorSnapshot] | None = None

        def evaluate(
            self, bars: Sequence[DailyBar], snapshot: IndicatorSnapshot
        ) -> ScreeningResult:
            self.called_with = (bars, snapshot)
            return BreakoutStrategy().evaluate(bars, snapshot)

    market_bars = bars_with_latest()
    snapshot = indicators()
    strategy = StubStrategy()

    result = ScreeningEngine(strategy).evaluate(market_bars, snapshot)

    assert strategy.called_with == (market_bars, snapshot)
    assert result.passed is True
