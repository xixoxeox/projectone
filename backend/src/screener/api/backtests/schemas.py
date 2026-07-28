from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from screener.modules.backtest import BacktestStatus


class BacktestCreateRequest(BaseModel):
    strategy_name: str = Field(min_length=1, max_length=100)
    strategy_version: str | None = Field(default=None, max_length=100)
    parameters: dict[str, Any] = Field(default_factory=dict)
    start_date: date
    end_date: date
    data_as_of: datetime | None = None

    @field_validator("strategy_name")
    @classmethod
    def validate_strategy_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("strategy_name must not be blank")
        return value

    @field_validator("strategy_version")
    @classmethod
    def normalize_strategy_version(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

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
