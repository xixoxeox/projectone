from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SyncResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    job_name: str
    status: str
    inserted_rows: int
    updated_rows: int
    skipped_rows: int
    duration_ms: int


class SyncJobStatusResponse(BaseModel):
    job_name: str
    enabled: bool
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_cursor: str | None


class SyncJobRunResponse(BaseModel):
    id: int
    job_name: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    status: str
    inserted_rows: int
    updated_rows: int
    skipped_rows: int
    error_message: str | None
