from dataclasses import dataclass, field, replace
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
    strategy_version: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    data_as_of: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    failure_code: str | None = None
    failure_message: str | None = None

    @classmethod
    def create(
        cls,
        strategy_name: str,
        start_date: date,
        end_date: date,
        strategy_version: str | None = None,
        parameters: dict[str, Any] | None = None,
        data_as_of: datetime | None = None,
    ) -> "BacktestRun":
        strategy_name = strategy_name.strip()
        if not strategy_name:
            raise ValueError("strategy_name must not be blank")
        if strategy_version is not None:
            strategy_version = strategy_version.strip() or None
        if start_date > end_date:
            raise ValueError("start_date must be on or before end_date")
        if data_as_of is not None and (data_as_of.tzinfo is None or data_as_of.utcoffset() is None):
            raise ValueError("data_as_of must be timezone-aware")
        return cls(
            id=uuid4(),
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            parameters=dict(parameters or {}),
            start_date=start_date,
            end_date=end_date,
            data_as_of=data_as_of,
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

    def fail(
        self, failure_message: str, failure_code: str | None = None, at: datetime | None = None
    ) -> "BacktestRun":
        self._require(BacktestStatus.RUNNING, BacktestStatus.FAILED)
        return replace(
            self,
            status=BacktestStatus.FAILED,
            failure_code=failure_code,
            failure_message=failure_message,
            completed_at=at or datetime.now(UTC),
        )

    def _require(self, current: BacktestStatus, target: BacktestStatus) -> None:
        if self.status is not current:
            raise InvalidBacktestTransition(
                f"cannot transition from {self.status.value} to {target.value}"
            )
