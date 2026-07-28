"""Deterministic shared-cash portfolio accounting and execution.

Each snapshot is end-of-day. Exits (including final liquidation) precede entries,
then remaining positions are marked at the close. Missing bars carry the last close
observed after entry; a future close is never used.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.backtest.domain import (
    BacktestExitReason,
    BacktestRun,
    BacktestTrade,
    PortfolioSnapshot,
)
from screener.modules.backtest.executor import (
    MONEY,
    RATE,
    ZERO,
    BacktestExecutionResult,
    BacktestParameters,
    DailyBar,
    DuplicateDailyBarError,
    InvalidBacktestParameters,
)
from screener.modules.backtest.models import BacktestTradeRecord, PortfolioSnapshotRecord
from screener.modules.backtest.strategy import BacktestSignal, BacktestStrategy
from screener.modules.market.infrastructure.models import DailyBarRecord


class PortfolioSkipReason(StrEnum):
    MAX_OPEN_POSITIONS = "max_open_positions"
    DUPLICATE_SYMBOL = "duplicate_symbol"
    INSUFFICIENT_CASH = "insufficient_cash"
    MINIMUM_CASH_BUFFER = "minimum_cash_buffer"
    QUANTITY_ZERO = "quantity_zero"
    NO_ENTRY_BAR = "no_entry_bar"
    INVALID_PRICE = "invalid_price"


@dataclass(frozen=True, slots=True)
class PortfolioParameters:
    initial_capital: Decimal
    max_open_positions: int
    position_size_pct: Decimal
    minimum_cash_buffer_pct: Decimal
    position_sizing_mode: str
    trading: BacktestParameters

    @classmethod
    def parse(cls, values: dict[str, Any]) -> "PortfolioParameters":
        required = (
            "initial_capital",
            "max_open_positions",
            "position_sizing_mode",
            "position_size_pct",
            "minimum_cash_buffer_pct",
        )
        missing = [key for key in required if key not in values]
        if missing:
            raise InvalidBacktestParameters(f"portfolio mode requires: {', '.join(missing)}")
        if "position_size" in values:
            raise InvalidBacktestParameters("position_size is incompatible with portfolio mode")

        def dec(name: str) -> Decimal:
            value = values[name]
            if isinstance(value, bool):
                raise InvalidBacktestParameters(f"{name} must be numeric")
            try:
                result = Decimal(str(value))
            except (InvalidOperation, ValueError) as exc:
                raise InvalidBacktestParameters(f"{name} must be numeric") from exc
            if not result.is_finite():
                raise InvalidBacktestParameters(f"{name} must be finite")
            return result

        capital, size, buffer = (
            dec("initial_capital"),
            dec("position_size_pct"),
            dec("minimum_cash_buffer_pct"),
        )
        maximum = values["max_open_positions"]
        if capital <= 0:
            raise InvalidBacktestParameters("initial_capital must be greater than zero")
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
            raise InvalidBacktestParameters("max_open_positions must be a positive integer")
        if not ZERO < size <= 1:
            raise InvalidBacktestParameters(
                "position_size_pct must be greater than zero and at most one"
            )
        if not ZERO <= buffer < 1:
            raise InvalidBacktestParameters(
                "minimum_cash_buffer_pct must be at least zero and less than one"
            )
        if values["position_sizing_mode"] != "fixed_fraction":
            raise InvalidBacktestParameters("position_sizing_mode must be fixed_fraction")
        # Reuse all trading-cost and exit validation, supplying a harmless independent notional.
        common = dict(values)
        common["position_size"] = capital
        trading = BacktestParameters.parse(common)
        return cls(capital, maximum, size, buffer, "fixed_fraction", trading)


@dataclass(slots=True)
class OpenPosition:
    signal: BacktestSignal
    entry_date: date
    entry_raw_price: Decimal
    entry_price: Decimal
    quantity: int
    buy_commission: Decimal
    last_close: Decimal
    holding_days: int = 0

    @property
    def cost(self) -> Decimal:
        return self.entry_price * self.quantity + self.buy_commission


@dataclass(slots=True)
class PortfolioState:
    initial_capital: Decimal
    cash: Decimal
    running_peak: Decimal
    realized_pnl: Decimal = ZERO
    positions: dict[str, OpenPosition] = field(default_factory=dict)

    @classmethod
    def create(cls, capital: Decimal) -> "PortfolioState":
        if capital <= 0:
            raise ValueError("initial capital must be positive")
        return cls(capital, capital, capital)

    def equity(self) -> Decimal:
        return self.cash + sum((p.last_close * p.quantity for p in self.positions.values()), ZERO)


def affordable_quantity(
    target: Decimal, cash: Decimal, buffer: Decimal, price: Decimal, commission_rate: Decimal
) -> tuple[int, PortfolioSkipReason | None]:
    """Size whole shares; commission is included and quantity decremented until affordable."""
    if price <= 0 or not price.is_finite():
        return 0, PortfolioSkipReason.INVALID_PRICE
    spendable = cash - buffer
    if spendable <= 0:
        return 0, PortfolioSkipReason.MINIMUM_CASH_BUFFER
    allowed = min(target, spendable)
    quantity = int((allowed / price).to_integral_value(rounding=ROUND_DOWN))
    while quantity > 0 and price * quantity * (1 + commission_rate) > allowed:
        quantity -= 1
    if quantity <= 0:
        return (
            0,
            PortfolioSkipReason.QUANTITY_ZERO
            if allowed < price
            else PortfolioSkipReason.INSUFFICIENT_CASH,
        )
    return quantity, None


def exit_terms(
    position: OpenPosition, bar: DailyBar, p: BacktestParameters, final: bool
) -> tuple[BacktestExitReason, Decimal] | None:
    if final:
        return BacktestExitReason.END_OF_PERIOD, bar.close
    stop = position.entry_price * (1 - p.stop_loss_pct)
    target = position.entry_price * (1 + p.take_profit_pct)
    if bar.open <= stop or bar.low <= stop:
        return BacktestExitReason.STOP_LOSS, bar.open if bar.open <= stop else stop
    if bar.open >= target or bar.high >= target:
        return BacktestExitReason.TAKE_PROFIT, bar.open if bar.open >= target else target
    if position.holding_days >= p.max_holding_days:
        return BacktestExitReason.MAX_HOLDING_DAYS, bar.close
    return None


class PortfolioBacktestExecutor:
    def __init__(self, session: AsyncSession, strategy: BacktestStrategy) -> None:
        self.session, self.strategy = session, strategy

    async def execute(self, run: BacktestRun) -> BacktestExecutionResult:
        p = PortfolioParameters.parse(run.parameters)
        signals = sorted(
            await self.strategy.generate_signals(run), key=lambda s: (s.signal_date, s.symbol)
        )
        symbols = sorted({s.symbol for s in signals})
        rows = (
            list(
                await self.session.scalars(
                    select(DailyBarRecord)
                    .where(
                        DailyBarRecord.trading_date >= run.start_date,
                        DailyBarRecord.trading_date <= run.end_date,
                        DailyBarRecord.symbol.in_(symbols),
                    )
                    .order_by(DailyBarRecord.trading_date, DailyBarRecord.symbol)
                )
            )
            if symbols
            else []
        )
        by_date: dict[date, dict[str, DailyBar]] = {}
        seen: set[tuple[str, date]] = set()
        for row in rows:
            key = row.symbol, row.trading_date
            if key in seen:
                raise DuplicateDailyBarError(
                    f"duplicate daily bar: {row.symbol} {row.trading_date}"
                )
            seen.add(key)
            by_date.setdefault(row.trading_date, {})[row.symbol] = DailyBar(
                row.symbol, row.trading_date, row.open, row.high, row.low, row.close
            )
        dates = sorted(by_date)
        entry_events: dict[date, list[BacktestSignal]] = {}
        skips: dict[str, int] = {}
        for signal in signals:
            entry_date = next(
                (
                    day
                    for day in dates
                    if day > signal.signal_date and signal.symbol in by_date[day]
                ),
                None,
            )
            if entry_date is None:
                skips[PortfolioSkipReason.NO_ENTRY_BAR.value] = (
                    skips.get(PortfolioSkipReason.NO_ENTRY_BAR.value, 0) + 1
                )
            else:
                entry_events.setdefault(entry_date, []).append(signal)
        state = PortfolioState.create(p.initial_capital)
        trades: list[BacktestTrade] = []
        snapshots: list[PortfolioSnapshot] = []
        maximum_open = 0
        utilization_sum = ZERO
        for day in dates:
            bars = by_date[day]
            final = day == dates[-1]
            # Existing positions exit before any entries. A missing bar carries its prior close.
            for symbol in sorted(list(state.positions)):
                position = state.positions[symbol]
                bar = bars.get(symbol)
                if bar is None and final:
                    # Forced liquidation uses the last close known since entry; never a future bar.
                    bar = DailyBar(
                        symbol,
                        day,
                        position.last_close,
                        position.last_close,
                        position.last_close,
                        position.last_close,
                    )
                if bar is None:
                    continue
                position.last_close = bar.close
                position.holding_days += 1
                terms = exit_terms(position, bar, p.trading, final)
                if terms is None:
                    continue
                reason, raw_exit = terms
                exit_price = raw_exit * (1 - p.trading.slippage_rate)
                sell_notional = exit_price * position.quantity
                sell_commission = sell_notional * p.trading.commission_rate
                tax = sell_notional * p.trading.sell_tax_rate
                state.cash += sell_notional - sell_commission - tax
                gross = (exit_price - position.entry_price) * position.quantity
                commission = position.buy_commission + sell_commission
                net = gross - commission - tax
                state.realized_pnl += net
                trades.append(
                    BacktestTrade(
                        uuid4(),
                        run.id,
                        symbol,
                        position.signal.signal_date,
                        position.entry_date,
                        position.entry_price.quantize(MONEY),
                        position.quantity,
                        day,
                        exit_price.quantize(MONEY),
                        reason,
                        gross.quantize(MONEY),
                        commission.quantize(MONEY),
                        tax.quantize(MONEY),
                        (
                            (
                                (position.entry_price - position.entry_raw_price)
                                + (raw_exit - exit_price)
                            )
                            * position.quantity
                        ).quantize(MONEY),
                        net.quantize(MONEY),
                        position.holding_days,
                    )
                )
                del state.positions[symbol]
            if not final:
                for signal in sorted(
                    entry_events.get(day, []), key=lambda s: (s.signal_date, s.symbol)
                ):
                    skip_reason: PortfolioSkipReason | None = None
                    if signal.symbol in state.positions:
                        skip_reason = PortfolioSkipReason.DUPLICATE_SYMBOL
                    elif len(state.positions) >= p.max_open_positions:
                        skip_reason = PortfolioSkipReason.MAX_OPEN_POSITIONS
                    bar = bars[signal.symbol]
                    effective = bar.open * (1 + p.trading.slippage_rate)
                    if skip_reason is None:
                        equity = state.equity()
                        buffer = p.initial_capital * p.minimum_cash_buffer_pct
                        quantity, skip_reason = affordable_quantity(
                            equity * p.position_size_pct,
                            state.cash,
                            buffer,
                            effective,
                            p.trading.commission_rate,
                        )
                    else:
                        quantity = 0
                    if skip_reason is not None:
                        skips[skip_reason.value] = skips.get(skip_reason.value, 0) + 1
                        continue
                    commission = effective * quantity * p.trading.commission_rate
                    required = effective * quantity + commission
                    if required > state.cash:
                        skips[PortfolioSkipReason.INSUFFICIENT_CASH.value] = (
                            skips.get(PortfolioSkipReason.INSUFFICIENT_CASH.value, 0) + 1
                        )
                        continue
                    state.cash -= required
                    state.positions[signal.symbol] = OpenPosition(
                        signal, day, bar.open, effective, quantity, commission, bar.close
                    )
                    maximum_open = max(maximum_open, len(state.positions))
            market = sum((pos.last_close * pos.quantity for pos in state.positions.values()), ZERO)
            unrealized = sum(
                ((pos.last_close * pos.quantity) - pos.cost for pos in state.positions.values()),
                ZERO,
            )
            equity = state.cash + market
            state.running_peak = max(state.running_peak, equity)
            drawdown = state.running_peak - equity
            utilization_sum += market / equity if equity else ZERO
            snapshots.append(
                PortfolioSnapshot(
                    uuid4(),
                    run.id,
                    day,
                    state.cash.quantize(MONEY),
                    market.quantize(MONEY),
                    state.realized_pnl.quantize(MONEY),
                    unrealized.quantize(MONEY),
                    equity.quantize(MONEY),
                    ((equity / p.initial_capital) - 1).quantize(RATE),
                    state.running_peak.quantize(MONEY),
                    drawdown.quantize(MONEY),
                    (drawdown / state.running_peak).quantize(RATE),
                    len(state.positions),
                )
            )
        self.session.add_all(
            [
                BacktestTradeRecord(
                    **{
                        name: getattr(t, name)
                        for name in (
                            "id",
                            "run_id",
                            "symbol",
                            "signal_date",
                            "entry_date",
                            "entry_price",
                            "quantity",
                            "exit_date",
                            "exit_price",
                            "exit_reason",
                            "gross_pnl",
                            "commission",
                            "tax",
                            "slippage_cost",
                            "net_pnl",
                            "holding_days",
                        )
                    }
                )
                for t in trades
            ]
        )
        self.session.add_all(
            [
                PortfolioSnapshotRecord(
                    **{
                        name: getattr(s, name)
                        for name in (
                            "id",
                            "run_id",
                            "trading_date",
                            "cash",
                            "market_value",
                            "realized_pnl",
                            "unrealized_pnl",
                            "total_equity",
                            "cumulative_return",
                            "running_peak_equity",
                            "drawdown",
                            "drawdown_pct",
                            "open_position_count",
                        )
                    }
                )
                for s in snapshots
            ]
        )
        await self.session.flush()
        final_equity = snapshots[-1].total_equity if snapshots else p.initial_capital
        max_dd = max((s.drawdown for s in snapshots), default=ZERO)
        max_dd_pct = max((s.drawdown_pct for s in snapshots), default=ZERO)
        metrics = {
            "initial_capital": str(p.initial_capital.quantize(MONEY)),
            "final_equity": str(final_equity.quantize(MONEY)),
            "final_cash": str(state.cash.quantize(MONEY)),
            "net_profit": str((final_equity - p.initial_capital).quantize(MONEY)),
            "total_return": str(((final_equity / p.initial_capital) - 1).quantize(RATE)),
            "max_drawdown": str(max_dd.quantize(MONEY)),
            "max_drawdown_pct": str(max_dd_pct.quantize(RATE)),
            "total_signals": len(signals),
            "entered_trades": len(trades),
            "skipped_signals": sum(skips.values()),
            "skip_reasons": skips,
            "maximum_open_positions_used": maximum_open,
            "average_capital_utilization": str(
                (utilization_sum / len(snapshots) if snapshots else ZERO).quantize(RATE)
            ),
        }
        return BacktestExecutionResult(metrics)
