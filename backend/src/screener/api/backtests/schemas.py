"""Request and response schemas for backtest lifecycle metadata."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from screener.modules.backtest import BacktestRun, BacktestStatus


class CreateBacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_name: str = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_date_range(self) -> "CreateBacktestRequest":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if not self.strategy_name.strip():
            raise ValueError("strategy_name must not be blank")
        return self


class BacktestResponse(BaseModel):
    id: UUID
    strategy_name: str
    start_date: date
    end_date: date
    parameters: dict[str, Any]
    status: BacktestStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None

    @classmethod
    def from_run(cls, run: BacktestRun) -> "BacktestResponse":
        return cls.model_validate(run, from_attributes=True)
