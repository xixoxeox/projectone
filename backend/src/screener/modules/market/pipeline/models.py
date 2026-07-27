import uuid
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel


class PipelineStage(StrEnum):
    RESOLVING_TRADING_DATE = "resolving_trading_date"
    DUPLICATE_CHECK = "duplicate_check"
    MARKET_SYNC = "market_sync"
    INDICATOR_CALCULATION = "indicator_calculation"
    SCREENING = "screening"
    CANDIDATE_SCANNING = "candidate_scanning"
    CANDIDATE_RANKING = "candidate_ranking"
    WATCHLIST_PERSISTENCE = "watchlist_persistence"
    COMPLETED = "completed"


class ExecutionStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class TriggerType(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class PipelineResult(BaseModel):
    execution_id: uuid.UUID | None = None
    trading_date: date
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None = None
    stage: PipelineStage
    candidate_count: int | None = None
    persisted_count: int | None = None
    skipped_reason: str | None = None
    error_code: str | None = None
