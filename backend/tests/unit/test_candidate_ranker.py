from copy import deepcopy
from decimal import Decimal

import pytest

from screener.modules.market.ranking import CandidateRanker, RankedCandidate
from screener.modules.market.screening.models import ScreeningResult


def result(
    symbol: str = "TEST",
    *,
    passed: bool = True,
    metrics: dict[str, Decimal] | None = None,
) -> ScreeningResult:
    return ScreeningResult(
        symbol=symbol,
        passed=passed,
        metrics=metrics
        if metrics is not None
        else {
            "sma20": Decimal("110"),
            "sma60": Decimal("100"),
            "close": Decimal("105"),
            "previous_high20": Decimal("100"),
            "volume": Decimal("200"),
            "avg_volume20": Decimal("100"),
            "atr14": Decimal("4.2"),
        },
    )


def score(metrics: dict[str, str], component: str) -> tuple[Decimal, list[str]]:
    candidate = CandidateRanker().rank(
        [result(metrics={name: Decimal(value) for name, value in metrics.items()})]
    )[0]
    return candidate.component_scores[component], candidate.warnings


def test_empty_input_returns_empty_list() -> None:
    assert CandidateRanker().rank([]) == []


def test_single_candidate_has_known_scores_and_does_not_mutate_source() -> None:
    source = result()
    before = source.model_dump()

    ranked = CandidateRanker().rank([source])

    assert ranked == [
        RankedCandidate(
            symbol="TEST",
            rank=1,
            total_score=Decimal("57.50"),
            component_scores={
                "trend": Decimal("50.00"),
                "breakout": Decimal("50.00"),
                "volume": Decimal("50.00"),
                "volatility": Decimal("100.00"),
            },
            source_result=source,
        )
    ]
    assert ranked[0].source_result is source
    assert source.model_dump() == before


def test_multiple_candidates_sort_descending_and_receive_consecutive_ranks() -> None:
    weak = result("WEAK", metrics={})
    medium = result("MEDIUM")
    strong = result(
        "STRONG",
        metrics={
            "sma20": Decimal("120"),
            "sma60": Decimal("100"),
            "close": Decimal("110"),
            "previous_high20": Decimal("100"),
            "volume": Decimal("300"),
            "avg_volume20": Decimal("100"),
            "atr14": Decimal("5"),
        },
    )

    ranked = CandidateRanker().rank([weak, medium, strong])

    assert [candidate.symbol for candidate in ranked] == ["STRONG", "MEDIUM", "WEAK"]
    assert [candidate.rank for candidate in ranked] == [1, 2, 3]


def test_equal_scores_preserve_input_order() -> None:
    ranked = CandidateRanker().rank([result("B"), result("A"), result("C", metrics={})])

    assert [candidate.symbol for candidate in ranked] == ["B", "A", "C"]
    assert [candidate.rank for candidate in ranked] == [1, 2, 3]


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        ({"sma20": "100", "sma60": "100"}, "0.00"),
        ({"sma20": "110", "sma60": "100"}, "50.00"),
        ({"sma20": "120", "sma60": "100"}, "100.00"),
        ({"sma20": "130", "sma60": "100"}, "100.00"),
    ],
)
def test_trend_score_boundaries(metrics: dict[str, str], expected: str) -> None:
    assert score(metrics, "trend")[0] == Decimal(expected)


@pytest.mark.parametrize(
    "metrics", [{"sma20": "100", "sma60": "0"}, {"sma20": "100"}, {"sma60": "100"}]
)
def test_invalid_or_missing_trend_metrics_warn(metrics: dict[str, str]) -> None:
    component, warnings = score(metrics, "trend")
    assert component == Decimal("0.00")
    assert any(warning.startswith("trend score unavailable:") for warning in warnings)


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        ({"close": "100", "previous_high20": "100"}, "0.00"),
        ({"close": "105", "previous_high20": "100"}, "50.00"),
        ({"close": "110", "previous_high20": "100"}, "100.00"),
        ({"close": "120", "previous_high20": "100"}, "100.00"),
    ],
)
def test_breakout_score_boundaries(metrics: dict[str, str], expected: str) -> None:
    assert score(metrics, "breakout")[0] == Decimal(expected)


@pytest.mark.parametrize(
    "metrics",
    [{"close": "100", "previous_high20": "0"}, {"close": "100"}, {"previous_high20": "100"}],
)
def test_invalid_or_missing_breakout_metrics_warn(metrics: dict[str, str]) -> None:
    component, warnings = score(metrics, "breakout")
    assert component == Decimal("0.00")
    assert any(warning.startswith("breakout score unavailable:") for warning in warnings)


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        ({"volume": "100", "avg_volume20": "100"}, "0.00"),
        ({"volume": "200", "avg_volume20": "100"}, "50.00"),
        ({"volume": "300", "avg_volume20": "100"}, "100.00"),
        ({"volume": "400", "avg_volume20": "100"}, "100.00"),
    ],
)
def test_volume_score_boundaries(metrics: dict[str, str], expected: str) -> None:
    assert score(metrics, "volume")[0] == Decimal(expected)


@pytest.mark.parametrize(
    "metrics",
    [
        {"volume": "100", "avg_volume20": "0"},
        {"volume": "-1", "avg_volume20": "100"},
        {"volume": "100"},
        {"avg_volume20": "100"},
    ],
)
def test_invalid_or_missing_volume_metrics_warn(metrics: dict[str, str]) -> None:
    component, warnings = score(metrics, "volume")
    assert component == Decimal("0.00")
    assert any(warning.startswith("volume score unavailable:") for warning in warnings)


@pytest.mark.parametrize(
    ("atr", "expected"),
    [
        ("1", "0.00"),
        ("2", "50.00"),
        ("3", "100.00"),
        ("4.5", "100.00"),
        ("6", "100.00"),
        ("9", "50.00"),
        ("12", "0.00"),
        ("15", "0.00"),
    ],
)
def test_volatility_score_boundaries(atr: str, expected: str) -> None:
    assert score({"atr14": atr, "close": "100"}, "volatility")[0] == Decimal(expected)


@pytest.mark.parametrize(
    "metrics", [{"close": "100"}, {"atr14": "1", "close": "0"}, {"atr14": "-1", "close": "100"}]
)
def test_invalid_or_missing_volatility_metrics_warn(metrics: dict[str, str]) -> None:
    component, warnings = score(metrics, "volatility")
    assert component == Decimal("0.00")
    assert any(warning.startswith("volatility score unavailable:") for warning in warnings)


def test_repeating_decimal_scores_are_decimal_and_quantized() -> None:
    ranked = CandidateRanker().rank(
        [
            result(
                metrics={
                    "sma20": Decimal("101"),
                    "sma60": Decimal("99"),
                    "close": Decimal("103"),
                    "previous_high20": Decimal("99"),
                    "volume": Decimal("4"),
                    "avg_volume20": Decimal("3"),
                    "atr14": Decimal("2"),
                }
            )
        ]
    )[0]

    assert ranked.component_scores == {
        "trend": Decimal("10.10"),
        "breakout": Decimal("40.40"),
        "volume": Decimal("16.67"),
        "volatility": Decimal("47.09"),
    }
    assert ranked.total_score == Decimal("26.38")
    assert isinstance(ranked.total_score, Decimal)
    assert all(isinstance(value, Decimal) for value in ranked.component_scores.values())
    assert all(value.as_tuple().exponent == -2 for value in ranked.component_scores.values())


def test_missing_metric_zeroes_only_affected_component() -> None:
    candidate = CandidateRanker().rank(
        [result(metrics={"sma20": Decimal("120"), "sma60": Decimal("100")})]
    )[0]

    assert candidate.component_scores["trend"] == Decimal("100.00")
    assert candidate.total_score == Decimal("30.00")
    assert "breakout score unavailable: missing close" in candidate.warnings


def test_failed_result_is_rejected() -> None:
    with pytest.raises(ValueError, match="did not pass"):
        CandidateRanker().rank([result(passed=False)])


@pytest.mark.parametrize("symbol", ["", "   "])
def test_blank_symbol_is_rejected(symbol: str) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        CandidateRanker().rank([result(symbol)])


def test_duplicate_symbol_is_rejected_and_named() -> None:
    with pytest.raises(ValueError, match="duplicate symbol: DUP"):
        CandidateRanker().rank([result("DUP"), result("DUP")])


def test_all_inputs_are_validated_before_scoring_and_remain_unchanged() -> None:
    sources = [result("VALID"), result("FAILED", passed=False)]
    before = deepcopy([source.model_dump() for source in sources])

    with pytest.raises(ValueError):
        CandidateRanker().rank(sources)

    assert [source.model_dump() for source in sources] == before
