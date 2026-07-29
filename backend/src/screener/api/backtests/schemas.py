from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from screener.modules.backtest import BacktestStatus
from screener.modules.backtest.domain import BacktestExitReason
from screener.modules.backtest.executor import BacktestParameters


class BacktestCreateRequest(BaseModel):
    strategy_name: Literal["watchlist_entry"]
    strategy_version: Literal["1"] | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    start_date: date
    end_date: date
    data_as_of: datetime | None = None
    execution_mode: Literal["independent", "portfolio"] = "independent"

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        return value

    @model_validator(mode="after")
    def validate_mode_parameters(self) -> "BacktestCreateRequest":
        values = {**self.parameters, "execution_mode": self.execution_mode}
        if self.execution_mode == "portfolio":
            from screener.modules.backtest.portfolio import PortfolioParameters

            PortfolioParameters.parse(values)
        else:
            incompatible = {
                "max_open_positions",
                "position_sizing_mode",
                "position_size_pct",
                "minimum_cash_buffer_pct",
            } & values.keys()
            if incompatible:
                raise ValueError("portfolio parameters are incompatible with independent mode")
            BacktestParameters.parse(values)
        return self

    @field_validator("data_as_of")
    @classmethod
    def validate_data_as_of(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("data_as_of must be timezone-aware")
        return value


class BacktestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    strategy_name: str
    strategy_version: str | None
    parameters: dict[str, Any]
    start_date: date
    end_date: date
    data_as_of: datetime | None
    status: BacktestStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    result: dict[str, Any] | None
    failure_code: str | None
    failure_message: str | None
    execution_mode: Literal["independent", "portfolio"]


class PortfolioSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    trading_date: date
    cash: Decimal
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_equity: Decimal
    cumulative_return: Decimal
    running_peak_equity: Decimal
    drawdown: Decimal
    drawdown_pct: Decimal
    open_position_count: int


class PortfolioResponse(BaseModel):
    run_id: UUID
    execution_mode: Literal["portfolio"] = "portfolio"
    initial_capital: Decimal
    final_equity: Decimal
    final_cash: Decimal
    net_profit: Decimal
    total_return: Decimal
    max_drawdown: Decimal
    max_drawdown_pct: Decimal
    maximum_open_positions_used: int
    average_capital_utilization: Decimal
    snapshots: list[PortfolioSnapshotResponse]


class BacktestTradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    run_id: UUID
    symbol: str
    signal_date: date
    entry_date: date
    entry_price: Decimal
    quantity: int
    exit_date: date
    exit_price: Decimal
    exit_reason: BacktestExitReason
    gross_pnl: Decimal
    commission: Decimal
    tax: Decimal
    slippage_cost: Decimal
    net_pnl: Decimal
    holding_days: int
    created_at: datetime


class _AnalysisModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AnalysisSummaryResponse(_AnalysisModel):
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: Decimal | None
    gross_profit: Decimal
    gross_loss: Decimal
    net_profit: Decimal
    average_trade_pnl: Decimal | None
    average_win: Decimal | None
    average_loss: Decimal | None
    largest_win: Decimal | None
    largest_loss: Decimal | None
    profit_factor: Decimal | None
    average_holding_days: Decimal | None
    max_consecutive_wins: int
    max_consecutive_losses: int
    max_realized_pnl_drawdown: Decimal


class CumulativePointResponse(_AnalysisModel):
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


class SymbolAnalysisResponse(_AnalysisModel):
    symbol: str
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


class ExitReasonAnalysisResponse(_AnalysisModel):
    exit_reason: BacktestExitReason
    trade_count: int
    trade_share: Decimal
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: Decimal | None
    net_profit: Decimal
    average_trade_pnl: Decimal | None
    average_holding_days: Decimal | None


class MonthAnalysisResponse(_AnalysisModel):
    month: str
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


class BacktestAnalysisResponse(_AnalysisModel):
    run_id: UUID
    trade_count: int
    summary: AnalysisSummaryResponse
    cumulative_realized_pnl: list[CumulativePointResponse]
    by_symbol: list[SymbolAnalysisResponse]
    by_exit_reason: list[ExitReasonAnalysisResponse]
    by_month: list[MonthAnalysisResponse]
