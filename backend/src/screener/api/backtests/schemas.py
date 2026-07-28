from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from screener.modules.backtest import BacktestStatus


class BacktestCreateRequest(BaseModel):
    strategy_name: str = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date


class BacktestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    strategy_name: str
    start_date: date
    end_date: date
    status: BacktestStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    result: dict[str, Any] | None
    error_message: str | None
