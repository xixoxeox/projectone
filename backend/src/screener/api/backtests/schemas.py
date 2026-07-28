"""Request and response schemas for backtest lifecycle metadata."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from screener.modules.backtest import BacktestRun, BacktestStatus


class CreateBacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy_name: str = Field(min_length=1, max_length=100)
    strategy_version: str | None = Field(default=None, max_length=50)
    start_date: date
    end_date: date
    parameters: dict[str, Any] = Field(default_factory=dict)
    data_as_of: datetime | None = None

    @field_validator("data_as_of")
    @classmethod
    def timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("data_as_of must include a timezone")
        return value

    @model_validator(mode="after")
    def valid_values(self) -> "CreateBacktestRequest":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if not self.strategy_name.strip():
            raise ValueError("strategy_name must not be blank")
        if self.strategy_version is not None and not self.strategy_version.strip():
            self.strategy_version = None
        return self


class BacktestResponse(BaseModel):
    id: UUID
    strategy_name: str
    strategy_version: str | None
    start_date: date
    end_date: date
    parameters: dict[str, Any]
    data_as_of: datetime | None
    status: BacktestStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None
    failure_message: str | None

    @classmethod
    def from_run(cls, run: BacktestRun) -> "BacktestResponse":
        return cls.model_validate(run, from_attributes=True)
