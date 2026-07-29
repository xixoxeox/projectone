"""Focused Sprint 19 configuration, scoring, aggregation, and ranking tests."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from screener.modules.market.indicators.models import ScreeningResult
from screener.modules.market.ranking.ranker import SwingCandidateRanker
from screener.modules.market.screening.swing import (
    SwingScreeningConfig,
    clamp_score,
    high_is_good,
    low_is_good,
    quantize_score,
    triangular_score,
)


def test_config_defaults_are_immutable_and_safe() -> None:
    config = SwingScreeningConfig()
    assert config.minimum_history_bars == 61
    assert config.snapshot()["minimum_close"] == "1000"
    with pytest.raises(FrozenInstanceError):
        config.box_lookback = 10  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"box_lookback": 0}, "positive"),
        ({"pullback_lookback": 4, "pullback_volume_lookback": 5}, "pullback"),
        ({"contraction_short_lookback": 21}, "contraction"),
        ({"minimum_history_bars": 20}, "unsafe"),
    ],
)
def test_config_rejects_unsafe_lookbacks(changes: dict[str, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        SwingScreeningConfig(**changes)  # type: ignore[arg-type]


def test_score_helpers_have_exact_decimal_boundaries() -> None:
    assert clamp_score(Decimal("-1")) == Decimal("0")
    assert quantize_score(Decimal("12.345")) == Decimal("12.35")
    assert high_is_good(Decimal("2"), Decimal("1"), Decimal("3")) == Decimal("50.00")
    assert low_is_good(Decimal("0.05"), Decimal("0.05"), Decimal("0.15")) == Decimal("100.00")
    assert low_is_good(Decimal("0.10"), Decimal("0.05"), Decimal("0.15")) == Decimal("50.00")
    assert low_is_good(Decimal("0.15"), Decimal("0.05"), Decimal("0.15")) == Decimal("0.00")
    assert low_is_good(Decimal("0.03"), Decimal("0.03"), Decimal("0.08")) == Decimal("100.00")
    assert low_is_good(Decimal("0.055"), Decimal("0.03"), Decimal("0.08")) == Decimal("50.00")
    assert triangular_score(
        Decimal(".06"), Decimal(".03"), Decimal(".06"), Decimal(".12")
    ) == Decimal("100.00")


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity")])
def test_score_helpers_reject_non_finite_values(value: Decimal) -> None:
    with pytest.raises(ValueError, match="finite"):
        quantize_score(value)


def result(symbol: str, *, total_setup: Decimal = Decimal("60")) -> ScreeningResult:
    return ScreeningResult(
        symbol=symbol,
        passed=True,
        matched_setups=["box_breakout"],
        primary_setup="box_breakout",
        setup_scores={
            "box_breakout": total_setup,
            "volatility_contraction_breakout": Decimal("95"),
        },
        metrics={
            "sma20": Decimal("110"),
            "sma60": Decimal("100"),
            "average_trading_value_20": Decimal("5000000000"),
            "atr_pct": Decimal(".03"),
        },
    )


def test_ranking_uses_only_matched_passing_setup_scores() -> None:
    ranked = SwingCandidateRanker().rank([result("005930")])[0]
    assert ranked.component_scores["setup"] == Decimal("60")
    assert ranked.total_score == Decimal("69.50")


def test_ranking_rejects_duplicates_and_uses_symbol_tie_breaker() -> None:
    ranker = SwingCandidateRanker()
    assert [item.symbol for item in ranker.rank([result("2"), result("1")])] == ["1", "2"]
    with pytest.raises(ValueError, match="duplicate"):
        ranker.rank([result("1"), result("1")])
