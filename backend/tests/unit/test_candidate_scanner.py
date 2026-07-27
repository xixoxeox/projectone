from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from screener.modules.market.domain import DailyBar
from screener.modules.market.indicators.models import IndicatorSnapshot
from screener.modules.market.scanning import CandidateScanner, ScanInput
from screener.modules.market.screening import ScreeningEngine, ScreeningResult


def bar(symbol: str) -> DailyBar:
    return DailyBar(
        symbol=symbol,
        trading_date=date(2026, 7, 27),
        open=Decimal("10"),
        high=Decimal("12"),
        low=Decimal("9"),
        close=Decimal("11"),
        volume=1_000,
        source="test",
        as_of=datetime(2026, 7, 27, tzinfo=UTC),
    )


class RecordingStrategy:
    def __init__(
        self,
        outcomes: dict[str, bool] | None = None,
        *,
        result_symbol: str | None = None,
        error: Exception | None = None,
    ) -> None:
        self.outcomes = outcomes or {}
        self.result_symbol = result_symbol
        self.error = error
        self.calls: list[tuple[Sequence[DailyBar], IndicatorSnapshot]] = []

    def evaluate(self, bars: Sequence[DailyBar], indicators: IndicatorSnapshot) -> ScreeningResult:
        self.calls.append((bars, indicators))
        if self.error is not None:
            raise self.error
        symbol = bars[-1].symbol if bars else ""
        return ScreeningResult(
            symbol=self.result_symbol if self.result_symbol is not None else symbol,
            passed=self.outcomes.get(symbol, False),
        )


def scan_input(symbol: str, snapshot: IndicatorSnapshot | None = None) -> ScanInput:
    return ScanInput(symbol=symbol, bars=[bar(symbol)], indicators=snapshot or IndicatorSnapshot())


def scanner(strategy: RecordingStrategy) -> CandidateScanner:
    return CandidateScanner(ScreeningEngine(strategy))


def test_multiple_passing_stocks_preserve_order() -> None:
    strategy = RecordingStrategy({"005930": True, "042700": True})

    results = scanner(strategy).scan([scan_input("005930"), scan_input("042700")])

    assert [result.symbol for result in results] == ["005930", "042700"]


def test_only_passing_stocks_are_returned_in_relative_order() -> None:
    strategy = RecordingStrategy({"005930": True, "000660": False, "042700": True})

    results = scanner(strategy).scan(
        [scan_input("005930"), scan_input("000660"), scan_input("042700")]
    )

    assert [result.symbol for result in results] == ["005930", "042700"]


def test_all_stocks_fail() -> None:
    assert scanner(RecordingStrategy()).scan([scan_input("005930"), scan_input("042700")]) == []


def test_empty_scan_input() -> None:
    assert scanner(RecordingStrategy()).scan([]) == []


def test_every_input_is_delegated_with_exact_objects() -> None:
    strategy = RecordingStrategy({"005930": True, "042700": True})
    first_snapshot = IndicatorSnapshot(sma20=Decimal("10"))
    second_snapshot = IndicatorSnapshot(sma20=Decimal("20"))
    first = scan_input("005930", first_snapshot)
    second = scan_input("042700", second_snapshot)

    scanner(strategy).scan([first, second])

    assert len(strategy.calls) == 2
    assert strategy.calls[0][0] is first.bars
    assert strategy.calls[0][1] is first_snapshot
    assert strategy.calls[1][0] is second.bars
    assert strategy.calls[1][1] is second_snapshot


def test_empty_bars_are_evaluated_and_failed_result_is_excluded() -> None:
    strategy = RecordingStrategy()
    empty_input = ScanInput(symbol="005930", bars=[], indicators=IndicatorSnapshot())
    candidate_scanner = scanner(strategy)

    normalized = candidate_scanner._evaluate(empty_input)
    assert normalized.symbol == "005930"
    assert normalized.passed is False
    assert candidate_scanner.scan([empty_input]) == []
    assert strategy.calls == [
        (empty_input.bars, empty_input.indicators),
        (empty_input.bars, empty_input.indicators),
    ]


@pytest.mark.parametrize("symbol", ["", "   "])
def test_blank_symbol_is_rejected(symbol: str) -> None:
    strategy = RecordingStrategy()

    with pytest.raises(ValueError, match="must not be blank"):
        scanner(strategy).scan([ScanInput(symbol, [], IndicatorSnapshot())])

    assert strategy.calls == []


def test_bar_symbol_mismatch_is_rejected_before_evaluation() -> None:
    strategy = RecordingStrategy()
    invalid = ScanInput("005930", [bar("000660")], IndicatorSnapshot())

    with pytest.raises(ValueError, match="does not match"):
        scanner(strategy).scan([invalid])

    assert strategy.calls == []


def test_mixed_bar_symbols_are_rejected_before_evaluation() -> None:
    strategy = RecordingStrategy()
    invalid = ScanInput("005930", [bar("005930"), bar("000660")], IndicatorSnapshot())

    with pytest.raises(ValueError, match="multiple symbols"):
        scanner(strategy).scan([invalid])

    assert strategy.calls == []


def test_duplicate_input_symbols_are_rejected() -> None:
    strategy = RecordingStrategy()

    with pytest.raises(ValueError, match="005930"):
        scanner(strategy).scan([scan_input("005930"), scan_input("005930")])

    assert strategy.calls == []


def test_strategy_result_symbol_mismatch_is_rejected() -> None:
    strategy = RecordingStrategy(result_symbol="000660")

    with pytest.raises(ValueError, match="does not match"):
        scanner(strategy).scan([scan_input("005930")])


def test_strategy_exceptions_are_not_suppressed() -> None:
    strategy = RecordingStrategy(error=RuntimeError("strategy failed"))

    with pytest.raises(RuntimeError, match="strategy failed"):
        scanner(strategy).scan([scan_input("005930")])
