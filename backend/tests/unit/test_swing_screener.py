from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.models import IndicatorSnapshot
from screener.modules.market.ranking.ranker import SwingCandidateRanker
from screener.modules.market.screening.models import ScreeningResult
from screener.modules.market.screening.swing import (
    BoxBreakoutStrategy,
    MultiSetupSwingStrategy,
    SwingSetup,
    high_is_good,
    low_is_good,
    quantize_score,
    triangular_score,
    true_range,
)

D = Decimal
BASE_CLOSE = D("10000")


def bars(count: int = 61, close: Decimal = BASE_CLOSE) -> list[DailyBar]:
    start = date(2026, 1, 1)
    return [
        DailyBar(
            symbol="AAA",
            trading_date=start + timedelta(days=n),
            open=close + D(n) - 1,
            high=close + D(n) + 1,
            low=close + D(n) - 2,
            close=close + D(n),
            volume=200000,
            source="fixture",
            as_of=datetime.now(UTC),
        )
        for n in range(count)
    ]


def indicators() -> IndicatorSnapshot:
    return IndicatorSnapshot(
        sma20=D("10020"),
        sma60=D("9000"),
        ema20=D("10020"),
        atr14=D("300"),
        avg_volume20=D("100000"),
    )


def test_exact_scoring_boundaries_and_interpolation() -> None:
    assert high_is_good(D("1.2"), D("1.2"), D("3")) == D("0.00")
    assert high_is_good(D("2.1"), D("1.2"), D("3")) == D("50.00")
    assert low_is_good(D(".05"), D(".05"), D(".15")) == D("100.00")
    assert low_is_good(D(".10"), D(".05"), D(".15")) == D("50.00")
    assert triangular_score(D(".03"), D(".03"), D(".06"), D(".12")) == D("0.00")
    assert triangular_score(D(".06"), D(".03"), D(".06"), D(".12")) == D("100.00")
    assert triangular_score(D(".09"), D(".03"), D(".06"), D(".12")) == D("50.00")
    assert quantize_score(D("50.005")) == D("50.01")
    assert quantize_score(D("1000")) == D("100.00")
    with pytest.raises(ValueError):
        quantize_score(D("NaN"))


def test_true_range_is_gap_aware() -> None:
    bar = bars(1)[0].model_copy(update={"high": D("110"), "low": D("100")})
    assert true_range(bar, D("90")) == D("20")


def test_box_previous_range_excludes_latest_without_mutation() -> None:
    source = bars(21)
    source[-1] = source[-1].model_copy(
        update={"high": D("999999"), "close": D("10025"), "open": D("10024"), "volume": 400000}
    )
    original = list(source)
    result = BoxBreakoutStrategy().evaluate(source, indicators())
    assert result.setup_metrics[SwingSetup.BOX_BREAKOUT]["previous_high20"] != D("999999")
    assert source == original


def test_common_filter_and_historical_defaults() -> None:
    result = MultiSetupSwingStrategy().evaluate(bars(20), indicators())
    assert not result.passed and "insufficient_history" in result.reasons[0]
    historical = ScreeningResult(symbol="OLD", passed=True)
    assert historical.matched_setups == [] and historical.primary_setup is None


def test_swing_ranker_uses_canonical_symbol_tie_break() -> None:
    def result(symbol: str) -> ScreeningResult:
        return ScreeningResult(
            symbol=symbol,
            passed=True,
            primary_setup="box_breakout",
            matched_setups=["box_breakout"],
            setup_scores={"box_breakout": D("50")},
            metrics={
                "sma20": D("120"),
                "sma60": D("100"),
                "average_trading_value_20": D("5000000000"),
                "atr_pct": D(".03"),
            },
        )

    ranked = SwingCandidateRanker().rank([result("BBB"), result("AAA")])
    assert [x.symbol for x in ranked] == ["AAA", "BBB"]
    assert [x.rank for x in ranked] == [1, 2]
