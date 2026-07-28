"""Canonical domain values produced by daily watchlist execution."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID


class TriggerType(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    RECOVERY = "recovery"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PipelineStage(StrEnum):
    UNKNOWN = "unknown"
    SYNC = "sync"
    SCANNING = "scanning"
    SCREENING = "screening"
    RANKING = "ranking"
    PERSISTENCE = "persistence"


@dataclass(frozen=True)
class PipelineResult:
    """Outcome shared by the pipeline and its application-boundary adapters."""

    trading_date: date
    execution_id: UUID
    trigger_type: TriggerType
    status: ExecutionStatus
    candidate_count: int = 0
    persisted_count: int = 0
    duration_seconds: float = 0
    stage: PipelineStage | None = None
    error_code: str | None = None
    recovered_execution_id: UUID | None = None

    @property
    def succeeded(self) -> bool:
        return self.status is ExecutionStatus.SUCCEEDED
