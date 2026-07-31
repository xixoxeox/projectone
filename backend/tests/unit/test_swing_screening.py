"""Focused Sprint 19 configuration, scoring, aggregation, and ranking tests."""

import asyncio
from collections.abc import Sequence
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from screener.api.screener import definitions
from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.models import IndicatorSnapshot, ScreeningResult
from screener.modules.market.ranking.ranker import SwingCandidateRanker
from screener.modules.market.scanning import CandidateScanner, ScanInput
from screener.modules.market.screening import ScreeningEngine
from screener.modules.market.screening.swing import (
    MultiSetupSwingStrategy,
    SwingScreeningConfig,
    _true_ranges,
    clamp_score,
    high_is_good,
    low_is_good,
    quantize_score,
    triangular_score,
)


def daily_bars(symbol: str = "005930", count: int = 61) -> list[DailyBar]:
    return [
        DailyBar(
            symbol=symbol,
            trading_date=date(2026, 5, 1) + timedelta(days=index),
            open=Decimal("10000"),
            high=Decimal("10100"),
            low=Decimal("9900"),
            close=Decimal("10000"),
            volume=200_000,
            source="test",
            as_of=datetime(2026, 5, 1, tzinfo=UTC) + timedelta(days=index),
        )
        for index in range(count)
    ]


def complete_indicators() -> IndicatorSnapshot:
    return IndicatorSnapshot(
        sma20=Decimal("9900"),
        sma60=Decimal("9800"),
        ema20=Decimal("9950"),
        atr14=Decimal("200"),
    )


def test_config_defaults_are_immutable_and_safe() -> None:
    config = SwingScreeningConfig()
    assert config.minimum_history_bars == 61
    assert config.snapshot()["minimum_close"] == "1000"
    with pytest.raises(FrozenInstanceError):
        config.box_lookback = 10  # type: ignore[misc]


def test_definitions_uses_the_app_owned_canonical_config() -> None:
    config = SwingScreeningConfig(maximum_candidates=7)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(swing_screening_config=config))
    )
    response = asyncio.run(definitions(None, request))  # type: ignore[arg-type]
    assert response["defaults"]["maximum_candidates"] == 7  # type: ignore[index]


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


def test_contraction_accepts_sufficient_daily_bar_history() -> None:
    passed, metrics, rules = MultiSetupSwingStrategy()._contraction(
        daily_bars(), complete_indicators()
    )

    assert passed is False
    assert metrics["prior_long_average_true_range"] == Decimal("200")
    assert rules["true_range"] is False


def test_true_ranges_have_one_observation_per_adjacent_pair() -> None:
    bars = daily_bars(count=23)

    assert len(_true_ranges(bars)) == len(bars) - 1


def test_true_ranges_include_previous_close_gaps() -> None:
    bars = daily_bars(count=3)
    bars[1] = bars[1].model_copy(
        update={
            "open": Decimal("11000"),
            "high": Decimal("11100"),
            "low": Decimal("10900"),
            "close": Decimal("11000"),
        }
    )
    bars[2] = bars[2].model_copy(
        update={
            "open": Decimal("10000"),
            "high": Decimal("10100"),
            "low": Decimal("9900"),
            "close": Decimal("10000"),
        }
    )

    assert _true_ranges(bars) == [Decimal("1100"), Decimal("1100")]


def test_full_swing_evaluation_completes_with_sufficient_history() -> None:
    result = MultiSetupSwingStrategy().evaluate(daily_bars(), complete_indicators())

    assert result.symbol == "005930"
    assert (
        "prior_long_average_true_range" in result.setup_metrics["volatility_contraction_breakout"]
    )


def test_candidate_scanner_evaluates_two_real_swing_inputs() -> None:
    class RecordingSwingStrategy(MultiSetupSwingStrategy):
        def __init__(self) -> None:
            super().__init__()
            self.evaluated_symbols: list[str] = []

        def evaluate(
            self, bars: Sequence[DailyBar], indicators: IndicatorSnapshot
        ) -> ScreeningResult:
            self.evaluated_symbols.append(bars[-1].symbol)
            return super().evaluate(bars, indicators)

    strategy = RecordingSwingStrategy()
    inputs = [
        ScanInput(symbol=symbol, bars=daily_bars(symbol), indicators=complete_indicators())
        for symbol in ("005930", "000660")
    ]

    CandidateScanner(ScreeningEngine(strategy)).scan(inputs)

    assert strategy.evaluated_symbols == ["005930", "000660"]


def test_contraction_insufficient_history_behavior_is_unchanged() -> None:
    assert MultiSetupSwingStrategy()._contraction(daily_bars(count=21), complete_indicators()) == (
        False,
        {"setup_score": Decimal("0")},
        {},
    )


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
