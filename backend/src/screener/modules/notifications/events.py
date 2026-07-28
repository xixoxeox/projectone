from datetime import date
from enum import StrEnum

from pydantic import BaseModel


class NotificationEventType(StrEnum):
    WATCHLIST_PUBLISHED = "watchlist.published"
    WATCHLIST_FAILED = "watchlist.failed"


class NotificationEvent(BaseModel):
    type: NotificationEventType
    trading_date: date
    execution_id: str | None = None
    candidate_count: int | None = None
    error_code: str | None = None
