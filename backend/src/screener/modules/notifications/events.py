"""Structured domain events emitted by watchlist execution boundaries."""

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from screener.modules.market.pipeline.models import PipelineStage, TriggerType


class EventBase(BaseModel):
    trading_date: date
    execution_id: UUID
    trigger_type: TriggerType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PipelineSucceededEvent(EventBase):
    event_type: Literal["pipeline_succeeded"] = "pipeline_succeeded"
    status: Literal["success"] = "success"
    candidate_count: int = Field(ge=0)
    persisted_count: int = Field(ge=0)
    duration_seconds: float = Field(ge=0)


class PipelineFailedEvent(EventBase):
    event_type: Literal["pipeline_failed"] = "pipeline_failed"
    status: Literal["failed"] = "failed"
    stage: PipelineStage
    error_code: str = Field(min_length=1)
    duration_seconds: float = Field(ge=0)


class PipelineRecoveredEvent(EventBase):
    event_type: Literal["pipeline_recovered"] = "pipeline_recovered"
    status: Literal["recovered"] = "recovered"
    recovered_execution_id: UUID


class PipelineManualRunEvent(EventBase):
    event_type: Literal["pipeline_manual_run"] = "pipeline_manual_run"
    status: Literal["started"] = "started"
    trigger_type: Literal[TriggerType.MANUAL] = TriggerType.MANUAL


NotificationEvent = (
    PipelineSucceededEvent | PipelineFailedEvent | PipelineRecoveredEvent | PipelineManualRunEvent
)
