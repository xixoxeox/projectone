"""Pure realized-trade analysis.

Trades are always ordered by ``exit_date``, ``symbol``, then ``id``.  A
breakeven trade resets both winning and losing streaks.  All calculations use
Decimal and describe realized trades only (never portfolio equity).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from screener.modules.backtest.domain import BacktestExitReason, BacktestTrade

ZERO = Decimal(0)


@dataclass(frozen=True)
class TradeStats:
    trade_count: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: Decimal | None
    gross_profit: Decimal
    gross_loss: Decimal
    net_profit: Decimal
    average_trade_pnl: Decimal | None
    average_holding_days: Decimal | None
    largest_win: Decimal | None
    largest_loss: Decimal | None


@dataclass(frozen=True)
class AnalysisSummary(TradeStats):
    average_win: Decimal | None
    average_loss: Decimal | None
    profit_factor: Decimal | None
    max_consecutive_wins: int
    max_consecutive_losses: int
    max_realized_pnl_drawdown: Decimal


@dataclass(frozen=True)
class CumulativePoint:
    sequence: int
    trade_id: UUID
    exit_date: date
    symbol: str
    exit_reason: BacktestExitReason
    net_pnl: Decimal
    cumulative_net_pnl: Decimal
    running_peak: Decimal
    realized_drawdown: Decimal
    realized_drawdown_pct: Decimal | None


@dataclass(frozen=True)
class SymbolAnalysis(TradeStats):
    symbol: str


@dataclass(frozen=True)
class ExitReasonAnalysis:
    exit_reason: BacktestExitReason
    trade_count: int
    trade_share: Decimal
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: Decimal
    net_profit: Decimal
    average_trade_pnl: Decimal
    average_holding_days: Decimal


@dataclass(frozen=True)
class MonthAnalysis(TradeStats):
    month: str


@dataclass(frozen=True)
class BacktestAnalysis:
    run_id: UUID
    trade_count: int
    summary: AnalysisSummary
    cumulative_realized_pnl: list[CumulativePoint]
    by_symbol: list[SymbolAnalysis]
    by_exit_reason: list[ExitReasonAnalysis]
    by_month: list[MonthAnalysis]


def _stats(trades: list[BacktestTrade]) -> TradeStats:
    wins = [t.net_pnl for t in trades if t.net_pnl > ZERO]
    losses = [t.net_pnl for t in trades if t.net_pnl < ZERO]
    count = len(trades)
    gross_profit, gross_loss = sum(wins, ZERO), sum(losses, ZERO)
    net = sum((t.net_pnl for t in trades), ZERO)
    return TradeStats(
        count,
        len(wins),
        len(losses),
        count - len(wins) - len(losses),
        Decimal(len(wins)) / count if count else None,
        gross_profit,
        gross_loss,
        net,
        net / count if count else None,
        sum((Decimal(t.holding_days) for t in trades), ZERO) / count if count else None,
        max(wins) if wins else None,
        min(losses) if losses else None,
    )


def _groups[K](
    trades: list[BacktestTrade], key: Callable[[BacktestTrade], K]
) -> dict[K, list[BacktestTrade]]:
    output: dict[K, list[BacktestTrade]] = {}
    for trade in trades:
        value = key(trade)
        output.setdefault(value, []).append(trade)
    return output


def analyze_backtest_trades(run_id: UUID, trades: list[BacktestTrade]) -> BacktestAnalysis:
    """Analyze a snapshot of persisted trades in canonical order."""
    ordered = sorted(trades, key=lambda t: (t.exit_date, t.symbol, t.id))
    stats = _stats(ordered)
    cumulative = ZERO
    peak = ZERO
    max_drawdown = ZERO
    points: list[CumulativePoint] = []
    current_wins = current_losses = max_wins = max_losses = 0
    for sequence, trade in enumerate(ordered, 1):
        cumulative += trade.net_pnl
        peak = max(peak, cumulative)
        drawdown = peak - cumulative
        max_drawdown = max(max_drawdown, drawdown)
        points.append(
            CumulativePoint(
                sequence,
                trade.id,
                trade.exit_date,
                trade.symbol,
                trade.exit_reason,
                trade.net_pnl,
                cumulative,
                peak,
                drawdown,
                drawdown / peak if peak > ZERO else None,
            )
        )
        if trade.net_pnl > ZERO:
            current_wins += 1
            current_losses = 0
            max_wins = max(max_wins, current_wins)
        elif trade.net_pnl < ZERO:
            current_losses += 1
            current_wins = 0
            max_losses = max(max_losses, current_losses)
        else:
            current_wins = current_losses = 0
    summary = AnalysisSummary(
        **stats.__dict__,
        average_win=stats.gross_profit / stats.winning_trades if stats.winning_trades else None,
        average_loss=stats.gross_loss / stats.losing_trades if stats.losing_trades else None,
        profit_factor=stats.gross_profit / abs(stats.gross_loss) if stats.gross_loss else None,
        max_consecutive_wins=max_wins,
        max_consecutive_losses=max_losses,
        max_realized_pnl_drawdown=max_drawdown,
    )
    symbols = [
        SymbolAnalysis(**_stats(group).__dict__, symbol=str(symbol))
        for symbol, group in _groups(ordered, lambda t: t.symbol).items()
    ]
    symbols.sort(key=lambda row: row.symbol)
    symbols.sort(key=lambda row: row.net_profit, reverse=True)
    reasons = []
    reason_groups = _groups(ordered, lambda t: t.exit_reason)
    for reason in BacktestExitReason:
        group = reason_groups.get(reason)
        if group:
            item = _stats(group)
            reasons.append(
                ExitReasonAnalysis(
                    reason,
                    item.trade_count,
                    Decimal(item.trade_count) / stats.trade_count,
                    item.winning_trades,
                    item.losing_trades,
                    item.breakeven_trades,
                    item.win_rate or ZERO,
                    item.net_profit,
                    item.average_trade_pnl or ZERO,
                    item.average_holding_days or ZERO,
                )
            )
    months = [
        MonthAnalysis(**_stats(group).__dict__, month=str(month))
        for month, group in _groups(ordered, lambda t: t.exit_date.strftime("%Y-%m")).items()
    ]
    months.sort(key=lambda row: row.month)
    return BacktestAnalysis(run_id, stats.trade_count, summary, points, symbols, reasons, months)
