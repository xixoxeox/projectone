from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        BacktestParameters.parse(value)
        return value

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
