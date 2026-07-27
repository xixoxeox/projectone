from datetime import UTC, date, datetime
from decimal import Decimal

from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.models import IndicatorSnapshot
from screener.modules.market.screening.engine import ScreeningEngine
from screener.modules.market.screening.strategies.breakout import BreakoutStrategy


def bar(*, close: str = "120", volume: int = 2_000) -> DailyBar:
    price = Decimal(close)
    return DailyBar(
        symbol="TEST",
        trading_date=date(2026, 7, 27),
        open=price - 1,
        high=price,
        low=price - 2,
        close=price,
        volume=volume,
        source="test",
        as_of=datetime(2026, 7, 27, tzinfo=UTC),
    )


def indicators(**updates: Decimal | None) -> IndicatorSnapshot:
    values: dict[str, Decimal | None] = {
        "sma20": Decimal("110"),
        "sma60": Decimal("100"),
        "highest20": Decimal("120"),
        "avg_volume20": Decimal("1000"),
    }
    values.update(updates)
    return IndicatorSnapshot.model_validate(values)


def evaluate(
    market_bar: DailyBar | None = None,
    snapshot: IndicatorSnapshot | None = None,
) -> tuple[bool, list[str]]:
    result = ScreeningEngine(BreakoutStrategy()).evaluate(
        [market_bar or bar()], snapshot or indicators()
    )
    return result.passed, result.reasons


def test_successful_breakout_passes_every_rule() -> None:
    passed, reasons = evaluate()

    assert passed is True
    assert len(reasons) == 4
    assert all(reason.startswith("PASSED:") for reason in reasons)


def test_insufficient_volume_fails_volume_rule() -> None:
    passed, reasons = evaluate(bar(volume=1_000))

    assert passed is False
    assert reasons[-1] == "FAILED: latest volume > AverageVolume20 (1000 vs 1000)"


def test_no_breakout_fails_highest_rule() -> None:
    passed, reasons = evaluate(bar(close="119"))

    assert passed is False
    assert reasons[2] == "FAILED: latest close >= Highest20 (119 vs 120)"


def test_trend_failure_reports_both_trend_rules() -> None:
    passed, reasons = evaluate(
        bar(close="105"), indicators(sma20=Decimal("110"), sma60=Decimal("115"))
    )

    assert passed is False
    assert reasons[0].startswith("FAILED: SMA20 > SMA60")
    assert reasons[1].startswith("FAILED: latest close > SMA20")


def test_insufficient_history_fails_unavailable_rules() -> None:
    passed, reasons = evaluate(snapshot=indicators(sma60=None, highest20=None, avg_volume20=None))

    assert passed is False
    assert reasons[0].endswith("(insufficient history)")
    assert reasons[2].endswith("(insufficient history)")
    assert reasons[3].endswith("(insufficient history)")
