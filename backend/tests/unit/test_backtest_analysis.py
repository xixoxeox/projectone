"""Exact, deterministic tests for persisted realized-trade analysis."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from screener.modules.backtest.analysis import analyze_backtest_trades
from screener.modules.backtest.domain import BacktestExitReason, BacktestTrade

RUN = UUID(int=999)


def trade(
    identifier: int,
    pnl: str,
    *,
    day: int = 1,
    symbol: str = "AAA",
    reason: BacktestExitReason = BacktestExitReason.TAKE_PROFIT,
    holding: int = 1,
) -> BacktestTrade:
    exit_date = date(2026, 1, 1) + timedelta(days=day)
    return BacktestTrade(
        UUID(int=identifier),
        RUN,
        symbol,
        exit_date - timedelta(days=2),
        exit_date - timedelta(days=1),
        Decimal("1.00000000"),
        1,
        exit_date,
        Decimal("1.00000000"),
        reason,
        Decimal(pnl),
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal(pnl),
        holding,
    )


def test_empty_analysis_obeys_every_null_rule() -> None:
    result = analyze_backtest_trades(RUN, [])
    assert result.trade_count == 0
    assert (
        result.summary.gross_profit
        == result.summary.gross_loss
        == result.summary.net_profit
        == Decimal(0)
    )
    assert result.summary.max_realized_pnl_drawdown == Decimal(0)
    assert result.summary.max_consecutive_wins == result.summary.max_consecutive_losses == 0
    for value in (
        result.summary.win_rate,
        result.summary.average_trade_pnl,
        result.summary.average_win,
        result.summary.average_loss,
        result.summary.largest_win,
        result.summary.largest_loss,
        result.summary.profit_factor,
        result.summary.average_holding_days,
    ):
        assert value is None
    assert (
        result.cumulative_realized_pnl
        == result.by_symbol
        == result.by_exit_reason
        == result.by_month
        == []
    )


@pytest.mark.parametrize(
    ("pnl", "counts"), [("7.1", (1, 0, 0)), ("-7.1", (0, 1, 0)), ("0", (0, 0, 1))]
)
def test_one_trade_classification_and_nulls(pnl: str, counts: tuple[int, int, int]) -> None:
    s = analyze_backtest_trades(RUN, [trade(1, pnl)]).summary
    assert (s.winning_trades, s.losing_trades, s.breakeven_trades) == counts
    assert s.average_win == (Decimal(pnl) if Decimal(pnl) > 0 else None)
    assert s.average_loss == (Decimal(pnl) if Decimal(pnl) < 0 else None)
    assert s.profit_factor == (None if Decimal(pnl) >= 0 else Decimal(0))


def test_exact_summary_large_small_mixed_and_streaks() -> None:
    values = [
        "9999999999999999.12345678",
        "0.00000001",
        "-3.00000000",
        "0",
        "-2.00000000",
        "4.00000000",
        "5.00000000",
    ]
    result = analyze_backtest_trades(
        RUN, [trade(i + 1, v, holding=i + 1) for i, v in enumerate(values)]
    )
    s = result.summary
    assert s.gross_profit == Decimal("10000000000000008.12345679")
    assert s.gross_loss == Decimal("-5.00000000")
    assert s.net_profit == Decimal("10000000000000003.12345679")
    assert s.average_trade_pnl == s.net_profit / Decimal(7)
    assert s.average_win == s.gross_profit / Decimal(4)
    assert s.average_loss == Decimal("-2.50000000")
    assert s.largest_win == Decimal("9999999999999999.12345678")
    assert s.largest_loss == Decimal("-3.00000000")
    assert s.profit_factor == s.gross_profit / Decimal(5)
    assert s.average_holding_days == Decimal(4)
    assert s.max_consecutive_wins == 2 and s.max_consecutive_losses == 1


def test_breakeven_resets_both_streaks() -> None:
    s = analyze_backtest_trades(
        RUN, [trade(i + 1, v) for i, v in enumerate(["1", "1", "0", "1", "-1", "-1", "0", "-1"])]
    ).summary
    assert s.max_consecutive_wins == 2 and s.max_consecutive_losses == 2


def test_cumulative_peak_drawdown_recovery_and_percentage_rules() -> None:
    r = analyze_backtest_trades(
        RUN, [trade(i + 1, v) for i, v in enumerate(["-2", "2", "5", "-3", "4"])]
    )
    assert [p.cumulative_net_pnl for p in r.cumulative_realized_pnl] == list(
        map(Decimal, ["-2", "0", "5", "2", "6"])
    )
    assert [p.running_peak for p in r.cumulative_realized_pnl] == list(
        map(Decimal, ["0", "0", "5", "5", "6"])
    )
    assert [p.realized_drawdown for p in r.cumulative_realized_pnl] == list(
        map(Decimal, ["2", "0", "0", "3", "0"])
    )
    assert [p.realized_drawdown_pct for p in r.cumulative_realized_pnl] == [
        None,
        None,
        Decimal(0),
        Decimal("0.6"),
        Decimal(0),
    ]
    assert r.summary.max_realized_pnl_drawdown == Decimal(3)


def test_canonical_order_same_date_symbol_and_uuid() -> None:
    rows = [
        trade(9, "1", day=2, symbol="AAA"),
        trade(3, "1", day=1, symbol="BBB"),
        trade(2, "1", day=1, symbol="AAA"),
        trade(1, "1", day=1, symbol="AAA"),
    ]
    assert [p.trade_id.int for p in analyze_backtest_trades(RUN, rows).cumulative_realized_pnl] == [
        1,
        2,
        3,
        9,
    ]


def test_group_aggregation_and_deterministic_ordering() -> None:
    rows = [
        trade(1, "-1", day=35, symbol="ZZZ", reason=BacktestExitReason.END_OF_PERIOD),
        trade(2, "2", day=2, symbol="BBB", reason=BacktestExitReason.STOP_LOSS),
        trade(3, "2", day=3, symbol="AAA", reason=BacktestExitReason.TAKE_PROFIT),
        trade(4, "0", day=4, symbol="AAA", reason=BacktestExitReason.STOP_LOSS),
    ]
    r = analyze_backtest_trades(RUN, rows)
    assert [(x.symbol, x.trade_count, x.net_profit) for x in r.by_symbol] == [
        ("AAA", 2, Decimal(2)),
        ("BBB", 1, Decimal(2)),
        ("ZZZ", 1, Decimal(-1)),
    ]
    assert [x.exit_reason for x in r.by_exit_reason] == [
        BacktestExitReason.STOP_LOSS,
        BacktestExitReason.TAKE_PROFIT,
        BacktestExitReason.END_OF_PERIOD,
    ]
    assert [(x.month, x.trade_count, x.net_profit) for x in r.by_month] == [
        ("2026-01", 3, Decimal(4)),
        ("2026-02", 1, Decimal(-1)),
    ]
    assert r.by_exit_reason[0].trade_share == Decimal("0.5")
