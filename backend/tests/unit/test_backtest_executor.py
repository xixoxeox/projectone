from datetime import date
from decimal import Decimal

import pytest

from screener.modules.backtest.domain import BacktestExitReason, BacktestRun
from screener.modules.backtest.executor import (
    BacktestParameters,
    DailyBar,
    InvalidBacktestParameters,
    calculate_metrics,
    simulate_signal,
)
from screener.modules.backtest.strategy import BacktestSignal


def bar(day: int, open_: str, high: str, low: str, close: str) -> DailyBar:
    values = (Decimal(value) for value in (open_, high, low, close))
    return DailyBar("AAA", date(2025, 1, day), *values)


def run() -> BacktestRun:
    return BacktestRun.create("watchlist_entry", date(2025, 1, 1), date(2025, 1, 31))


@pytest.mark.parametrize(
    "name",
    [
        "initial_capital",
        "position_size",
        "stop_loss_pct",
        "take_profit_pct",
        "commission_rate",
        "sell_tax_rate",
        "slippage_rate",
    ],
)
def test_parameters_reject_boolean_numbers(name: str) -> None:
    with pytest.raises(InvalidBacktestParameters):
        BacktestParameters.parse({name: True})


def test_next_bar_entry_and_conservative_stop_priority() -> None:
    trade = simulate_signal(
        run(),
        BacktestSignal("AAA", date(2025, 1, 1)),
        [
            bar(1, "50", "60", "40", "50"),
            bar(2, "100", "100", "100", "100"),
            bar(3, "100", "120", "90", "100"),
        ],
        BacktestParameters(slippage_rate=Decimal("0")),
    )
    assert not isinstance(trade, BacktestExitReason)
    assert trade.entry_date == date(2025, 1, 2)
    assert trade.exit_reason is BacktestExitReason.STOP_LOSS
    assert trade.exit_price == Decimal("95.00000000")


def test_gap_target_and_costs() -> None:
    trade = simulate_signal(
        run(),
        BacktestSignal("AAA", date(2025, 1, 1)),
        [bar(2, "100", "100", "100", "100"), bar(3, "120", "120", "120", "120")],
        BacktestParameters(slippage_rate=Decimal("0.001")),
    )
    assert not isinstance(trade, BacktestExitReason)
    assert trade.exit_reason is BacktestExitReason.TAKE_PROFIT
    assert trade.exit_price == Decimal("119.88000000")
    assert trade.commission > 0 and trade.tax > 0 and trade.slippage_cost > 0


def test_skips_and_empty_metrics() -> None:
    signal = BacktestSignal("AAA", date(2025, 1, 1))
    assert (
        simulate_signal(run(), signal, [], BacktestParameters()) is BacktestExitReason.NO_ENTRY_BAR
    )
    small = BacktestParameters(initial_capital=Decimal("10"), position_size=Decimal("10"))
    assert (
        simulate_signal(run(), signal, [bar(2, "100", "100", "100", "100")], small)
        is BacktestExitReason.INSUFFICIENT_POSITION_SIZE
    )
    metrics = calculate_metrics([], 2, BacktestParameters())
    assert metrics["profit_factor"] is None and metrics["skipped_signals"] == 2
