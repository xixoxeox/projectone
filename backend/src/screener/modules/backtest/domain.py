from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class BacktestStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class InvalidBacktestTransition(ValueError):
    """Raised when a backtest lifecycle transition is not allowed."""


@dataclass(frozen=True, slots=True)
class BacktestRun:
    id: UUID
    strategy_name: str
    start_date: date
    end_date: date
    status: BacktestStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None

    @classmethod
    def create(cls, strategy_name: str, start_date: date, end_date: date) -> "BacktestRun":
        if start_date > end_date:
            raise ValueError("start_date must be on or before end_date")
        return cls(
            id=uuid4(),
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            status=BacktestStatus.PENDING,
            created_at=datetime.now(UTC),
        )

    def start(self, at: datetime | None = None) -> "BacktestRun":
        self._require(BacktestStatus.PENDING, BacktestStatus.RUNNING)
        return replace(self, status=BacktestStatus.RUNNING, started_at=at or datetime.now(UTC))

    def complete(self, result: dict[str, Any], at: datetime | None = None) -> "BacktestRun":
        self._require(BacktestStatus.RUNNING, BacktestStatus.COMPLETED)
        return replace(
            self,
            status=BacktestStatus.COMPLETED,
            result=result,
            completed_at=at or datetime.now(UTC),
        )

    def fail(self, error_message: str, at: datetime | None = None) -> "BacktestRun":
        self._require(BacktestStatus.RUNNING, BacktestStatus.FAILED)
        return replace(
            self,
            status=BacktestStatus.FAILED,
            error_message=error_message,
            completed_at=at or datetime.now(UTC),
        )

    def _require(self, current: BacktestStatus, target: BacktestStatus) -> None:
        if self.status is not current:
            raise InvalidBacktestTransition(
                f"cannot transition from {self.status.value} to {target.value}"
            )
