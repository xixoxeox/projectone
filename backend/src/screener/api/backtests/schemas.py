from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from screener.modules.backtest import BacktestStatus
from screener.modules.backtest.domain import BacktestExitReason
from screener.modules.backtest.executor import BacktestParameters


class BacktestCreateRequest(BaseModel):
    strategy_name: str = Field(min_length=1, max_length=100)
    strategy_version: str | None = Field(default=None, max_length=100)
    parameters: dict[str, Any] = Field(default_factory=dict)
    start_date: date
    end_date: date
    data_as_of: datetime | None = None

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        BacktestParameters.parse(value)
        return value

    @field_validator("strategy_name")
    @classmethod
    def validate_strategy_name(cls, value: str) -> str:
        value = value.strip()
        if value != "watchlist_entry":
            raise ValueError("strategy_name must be 'watchlist_entry'")
        return value

    @field_validator("strategy_version")
    @classmethod
    def normalize_strategy_version(cls, value: str | None) -> str | None:
        value = value.strip() or None if value is not None else None
        if value not in (None, "1"):
            raise ValueError("strategy_version must be null or '1'")
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
