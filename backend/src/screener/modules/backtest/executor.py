from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.backtest.domain import BacktestExitReason, BacktestRun, BacktestTrade
from screener.modules.backtest.models import BacktestTradeRecord
from screener.modules.backtest.strategy import BacktestSignal, BacktestStrategy
from screener.modules.market.infrastructure.models import DailyBarRecord

ZERO = Decimal("0")
MONEY = Decimal("0.00000001")
RATE = Decimal("0.00000001")


class BacktestExecutionError(ValueError):
    failure_code = "BACKTEST_EXECUTION_ERROR"


class UnsupportedBacktestStrategy(BacktestExecutionError):
    """Raised when a run does not identify the executor's supported strategy."""

    failure_code = "UNSUPPORTED_STRATEGY"


def validate_strategy_contract(strategy_name: str, strategy_version: str | None) -> tuple[str, str]:
    """Validate and canonicalize the public v1 strategy identifier."""
    name = strategy_name.strip()
    version = strategy_version.strip() if strategy_version is not None else None
    if name != "watchlist_entry" or version not in (None, "1"):
        raise UnsupportedBacktestStrategy(
            "only strategy_name 'watchlist_entry' with strategy_version null or '1' is supported"
        )
    return name, "1"


class InvalidBacktestParameters(BacktestExecutionError):
    failure_code = "INVALID_PARAMETERS"


class DuplicateDailyBarError(BacktestExecutionError):
    failure_code = "DUPLICATE_DAILY_BAR"


@dataclass(frozen=True, slots=True)
class BacktestParameters:
    initial_capital: Decimal = Decimal("5000000")
    position_size: Decimal = Decimal("500000")
    stop_loss_pct: Decimal = Decimal("0.05")
    take_profit_pct: Decimal = Decimal("0.10")
    max_holding_days: int = 10
    commission_rate: Decimal = Decimal("0.00015")
    sell_tax_rate: Decimal = Decimal("0.0015")
    slippage_rate: Decimal = Decimal("0.001")

    @classmethod
    def parse(cls, values: dict[str, Any] | None) -> "BacktestParameters":
        supplied = values or {}
        defaults = cls()

        def decimal_value(name: str, default: Decimal) -> Decimal:
            value = supplied.get(name, default)
            if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
                raise InvalidBacktestParameters(f"{name} must be numeric")
            try:
                result = Decimal(str(value))
            except InvalidOperation as exc:
                raise InvalidBacktestParameters(f"{name} must be numeric") from exc
            if not result.is_finite():
                raise InvalidBacktestParameters(f"{name} must be finite")
            return result

        holding = supplied.get("max_holding_days", defaults.max_holding_days)
        if isinstance(holding, bool) or not isinstance(holding, int):
            raise InvalidBacktestParameters("max_holding_days must be an integer")
        result = cls(
            initial_capital=decimal_value("initial_capital", defaults.initial_capital),
            position_size=decimal_value("position_size", defaults.position_size),
            stop_loss_pct=decimal_value("stop_loss_pct", defaults.stop_loss_pct),
            take_profit_pct=decimal_value("take_profit_pct", defaults.take_profit_pct),
            max_holding_days=holding,
            commission_rate=decimal_value("commission_rate", defaults.commission_rate),
            sell_tax_rate=decimal_value("sell_tax_rate", defaults.sell_tax_rate),
            slippage_rate=decimal_value("slippage_rate", defaults.slippage_rate),
        )
        if result.initial_capital <= 0:
            raise InvalidBacktestParameters("initial_capital must be greater than zero")
        if result.position_size <= 0 or result.position_size > result.initial_capital:
            raise InvalidBacktestParameters(
                "position_size must be positive and no greater than initial_capital"
            )
        for name in ("commission_rate", "sell_tax_rate", "slippage_rate"):
            if not ZERO <= getattr(result, name) < 1:
                raise InvalidBacktestParameters(f"{name} must be at least zero and less than one")
        if not ZERO < result.stop_loss_pct < 1:
            raise InvalidBacktestParameters(
                "stop_loss_pct must be greater than zero and less than one"
            )
        if not ZERO < result.take_profit_pct < 10:
            raise InvalidBacktestParameters(
                "take_profit_pct must be greater than zero and less than ten"
            )
        if result.max_holding_days < 1:
            raise InvalidBacktestParameters("max_holding_days must be at least one")
        return result


@dataclass(frozen=True, slots=True)
class DailyBar:
    symbol: str
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True, slots=True)
class BacktestExecutionResult:
    metrics: dict[str, Any] = field(default_factory=dict)


class BacktestExecutor(Protocol):
    async def execute(self, run: BacktestRun) -> BacktestExecutionResult: ...


def simulate_signal(
    run: BacktestRun, signal: BacktestSignal, bars: list[DailyBar], p: BacktestParameters
) -> BacktestTrade | BacktestExitReason:
    eligible = sorted(
        (bar for bar in bars if signal.signal_date < bar.trading_date <= run.end_date),
        key=lambda b: b.trading_date,
    )
    if not eligible:
        return BacktestExitReason.NO_ENTRY_BAR
    entry_bar = eligible[0]
    entry_price = entry_bar.open * (1 + p.slippage_rate)
    quantity = int((p.position_size / entry_price).to_integral_value(rounding=ROUND_DOWN))
    if quantity < 1:
        return BacktestExitReason.INSUFFICIENT_POSITION_SIZE
    later = eligible[1:]
    if not later:
        exit_bar = entry_bar
        reason = BacktestExitReason.END_OF_PERIOD
        raw_exit = entry_bar.close
    else:
        stop = entry_price * (1 - p.stop_loss_pct)
        target = entry_price * (1 + p.take_profit_pct)
        exit_bar = later[-1]
        reason = BacktestExitReason.END_OF_PERIOD
        raw_exit = exit_bar.close
        for holding, bar in enumerate(later, 1):
            if bar.open <= stop or bar.low <= stop:
                exit_bar, reason = bar, BacktestExitReason.STOP_LOSS
                raw_exit = bar.open if bar.open <= stop else stop
                break
            if bar.open >= target or bar.high >= target:
                exit_bar, reason = bar, BacktestExitReason.TAKE_PROFIT
                raw_exit = bar.open if bar.open >= target else target
                break
            if holding >= p.max_holding_days:
                exit_bar, reason, raw_exit = bar, BacktestExitReason.MAX_HOLDING_DAYS, bar.close
                break
    exit_price = raw_exit * (1 - p.slippage_rate)
    gross = (exit_price - entry_price) * quantity
    buy_notional = entry_price * quantity
    sell_notional = exit_price * quantity
    commission = (buy_notional + sell_notional) * p.commission_rate
    tax = sell_notional * p.sell_tax_rate
    slippage = ((entry_price - entry_bar.open) + (raw_exit - exit_price)) * quantity
    return BacktestTrade(
        uuid4(),
        run.id,
        signal.symbol,
        signal.signal_date,
        entry_bar.trading_date,
        entry_price.quantize(MONEY),
        quantity,
        exit_bar.trading_date,
        exit_price.quantize(MONEY),
        reason,
        gross.quantize(MONEY),
        commission.quantize(MONEY),
        tax.quantize(MONEY),
        slippage.quantize(MONEY),
        (gross - commission - tax).quantize(MONEY),
        later.index(exit_bar) + 1 if later else 0,
    )


def calculate_metrics(
    trades: list[BacktestTrade], total_signals: int, p: BacktestParameters
) -> dict[str, Any]:
    ordered = sorted(trades, key=lambda t: (t.exit_date, t.entry_date, t.symbol, str(t.id)))
    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl < 0]
    gross_profit = sum((t.net_pnl for t in wins), ZERO)
    gross_loss = sum((t.net_pnl for t in losses), ZERO)
    net = sum((t.net_pnl for t in trades), ZERO)
    equity = p.initial_capital
    peak = equity
    drawdown = ZERO
    max_wins = max_losses = current_wins = current_losses = 0
    for trade in ordered:
        equity += trade.net_pnl
        peak = max(peak, equity)
        if peak:
            drawdown = max(drawdown, (peak - equity) / peak)
        if trade.net_pnl > 0:
            current_wins += 1
            current_losses = 0
            max_wins = max(max_wins, current_wins)
        elif trade.net_pnl < 0:
            current_losses += 1
            current_wins = 0
            max_losses = max(max_losses, current_losses)
    count = len(trades)

    def ratio(value: Decimal) -> str:
        return str(value.quantize(RATE))

    return {
        "initial_capital": str(p.initial_capital.quantize(MONEY)),
        "total_signals": total_signals,
        "entered_trades": count,
        "skipped_signals": total_signals - count,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": ratio(Decimal(len(wins)) / count) if count else ratio(ZERO),
        "gross_profit": str(gross_profit.quantize(MONEY)),
        "gross_loss": str(gross_loss.quantize(MONEY)),
        "net_profit": str(net.quantize(MONEY)),
        "total_return": ratio(net / p.initial_capital),
        "average_trade_return": ratio(
            sum((t.net_pnl / (t.entry_price * t.quantity) for t in trades), ZERO) / count
        )
        if count
        else ratio(ZERO),
        "average_holding_days": ratio(Decimal(sum(t.holding_days for t in trades)) / count)
        if count
        else ratio(ZERO),
        "profit_factor": ratio(gross_profit / abs(gross_loss)) if gross_loss else None,
        "max_drawdown": ratio(drawdown),
        "max_consecutive_wins": max_wins,
        "max_consecutive_losses": max_losses,
    }


class DatabaseBacktestExecutor:
    def __init__(self, session: AsyncSession, strategy: BacktestStrategy) -> None:
        self._session, self._strategy = session, strategy

    async def execute(self, run: BacktestRun) -> BacktestExecutionResult:
        requested_name, requested_version = validate_strategy_contract(
            run.strategy_name, run.strategy_version
        )
        if requested_name != self._strategy.name or requested_version != self._strategy.version:
            raise UnsupportedBacktestStrategy(
                f"executor strategy {self._strategy.name!r} version {self._strategy.version!r} "
                "does not match the requested strategy"
            )
        mode = run.parameters.get("execution_mode", "independent")
        if mode == "portfolio":
            from screener.modules.backtest.portfolio import PortfolioBacktestExecutor

            return await PortfolioBacktestExecutor(self._session, self._strategy).execute(run)
        if mode != "independent":
            raise InvalidBacktestParameters("execution_mode must be independent or portfolio")
        incompatible = {
            "max_open_positions",
            "position_sizing_mode",
            "position_size_pct",
            "minimum_cash_buffer_pct",
        } & run.parameters.keys()
        if incompatible:
            names = ", ".join(sorted(incompatible))
            raise InvalidBacktestParameters(
                f"portfolio parameters are incompatible with independent mode: {names}"
            )
        p = BacktestParameters.parse(run.parameters)
        signals = sorted(
            await self._strategy.generate_signals(run), key=lambda s: (s.signal_date, s.symbol)
        )
        symbols = sorted({s.symbol for s in signals})
        records = (
            []
            if not symbols
            else list(
                await self._session.scalars(
                    select(DailyBarRecord)
                    .where(
                        DailyBarRecord.symbol.in_(symbols),
                        DailyBarRecord.trading_date >= run.start_date,
                        DailyBarRecord.trading_date <= run.end_date,
                    )
                    .order_by(DailyBarRecord.symbol, DailyBarRecord.trading_date)
                )
            )
        )
        bars: dict[str, list[DailyBar]] = {symbol: [] for symbol in symbols}
        seen: set[tuple[str, date]] = set()
        for row in records:
            key = row.symbol, row.trading_date
            if key in seen:
                raise DuplicateDailyBarError(
                    f"duplicate daily bar: {row.symbol} {row.trading_date}"
                )
            seen.add(key)
            bars[row.symbol].append(
                DailyBar(row.symbol, row.trading_date, row.open, row.high, row.low, row.close)
            )
        trades = [
            result
            for signal in signals
            if isinstance(
                (result := simulate_signal(run, signal, bars.get(signal.symbol, []), p)),
                BacktestTrade,
            )
        ]
        records_to_add = [
            BacktestTradeRecord(
                id=t.id,
                run_id=t.run_id,
                symbol=t.symbol,
                signal_date=t.signal_date,
                entry_date=t.entry_date,
                entry_price=t.entry_price,
                quantity=t.quantity,
                exit_date=t.exit_date,
                exit_price=t.exit_price,
                exit_reason=t.exit_reason,
                gross_pnl=t.gross_pnl,
                commission=t.commission,
                tax=t.tax,
                slippage_cost=t.slippage_cost,
                net_pnl=t.net_pnl,
                holding_days=t.holding_days,
            )
            for t in trades
        ]
        # Isolate trade persistence in a savepoint.  A constraint/flush error can
        # then be recorded on the already-created run instead of poisoning the
        # outer transaction or, worse, allowing a completed status to be saved.
        async with self._session.begin_nested():
            self._session.add_all(records_to_add)
            await self._session.flush()
        return BacktestExecutionResult(calculate_metrics(trades, len(signals), p))
