from decimal import Decimal

import pytest

from screener.modules.backtest.executor import InvalidBacktestParameters
from screener.modules.backtest.portfolio import (
    PortfolioParameters,
    PortfolioSkipReason,
    PortfolioState,
    affordable_quantity,
)


def params(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "execution_mode": "portfolio",
        "initial_capital": "1000",
        "max_open_positions": 2,
        "position_sizing_mode": "fixed_fraction",
        "position_size_pct": "0.5",
        "minimum_cash_buffer_pct": "0.1",
    }
    values.update(overrides)
    return values


def test_initial_state_is_all_cash_with_positive_peak() -> None:
    state = PortfolioState.create(Decimal("1000"))
    assert state.cash == state.equity() == state.running_peak == Decimal("1000")
    assert state.positions == {}


def test_commission_aware_whole_share_affordability_decrements() -> None:
    quantity, reason = affordable_quantity(
        Decimal("100"), Decimal("100"), Decimal("0"), Decimal("10"), Decimal("0.01")
    )
    assert (quantity, reason) == (9, None)
    assert isinstance(quantity, int)


def test_cash_buffer_and_quantity_zero_are_stable() -> None:
    assert affordable_quantity(
        Decimal("10"), Decimal("100"), Decimal("100"), Decimal("1"), Decimal("0")
    ) == (0, PortfolioSkipReason.MINIMUM_CASH_BUFFER)
    assert affordable_quantity(
        Decimal("1"), Decimal("100"), Decimal("0"), Decimal("2"), Decimal("0")
    ) == (0, PortfolioSkipReason.QUANTITY_ZERO)


@pytest.mark.parametrize(
    "override",
    [
        {"initial_capital": "0"},
        {"max_open_positions": 0},
        {"position_size_pct": "1.1"},
        {"minimum_cash_buffer_pct": "1"},
        {"position_sizing_mode": "other"},
        {"position_size": "50"},
    ],
)
def test_invalid_portfolio_parameters(override: dict[str, object]) -> None:
    with pytest.raises(InvalidBacktestParameters):
        PortfolioParameters.parse(params(**override))
