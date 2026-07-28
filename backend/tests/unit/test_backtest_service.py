"""Backtest service lifecycle regression tests."""

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest

from screener.modules.backtest import (
    BacktestExecutionError,
    BacktestExecutionResult,
    BacktestRun,
    BacktestService,
    BacktestStatus,
    InvalidBacktestRangeError,
    InvalidBacktestTransitionError,
)

NOW = datetime(2026, 7, 28, 12, tzinfo=UTC)
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeRepository:
    def __init__(self) -> None:
        self.run: BacktestRun | None = None
        self.commits: list[BacktestStatus] = []

    async def create(
        self,
        strategy_name: str,
        strategy_version: str | None,
        start_date: date,
        end_date: date,
        parameters: dict[str, Any],
        data_as_of: datetime | None,
        created_at: datetime,
    ) -> BacktestRun:
        self.run = BacktestRun(
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            start_date=start_date,
            end_date=end_date,
            parameters=dict(parameters),
            data_as_of=data_as_of,
            created_at=created_at,
        )
        return self.run

    async def commit(self) -> None:
        assert self.run
        self.commits.append(self.run.status)

    async def get(self, run_id: UUID) -> BacktestRun | None:
        return self.run if self.run and self.run.id == run_id else None

    async def list(self, limit: int = 100, offset: int = 0) -> list[BacktestRun]:
        return [self.run] if self.run else []

    async def _mark(
        self, run_id: UUID, expected: BacktestStatus, status: BacktestStatus, **changes: Any
    ) -> BacktestRun:
        if not self.run or self.run.id != run_id or self.run.status != expected:
            raise InvalidBacktestTransitionError
        self.run = self.run.model_copy(update={"status": status, **changes})
        return self.run

    async def mark_running(self, run_id: UUID, started_at: datetime) -> BacktestRun:
        return await self._mark(
            run_id, BacktestStatus.PENDING, BacktestStatus.RUNNING, started_at=started_at
        )

    async def mark_completed(self, run_id: UUID, completed_at: datetime) -> BacktestRun:
        return await self._mark(
            run_id, BacktestStatus.RUNNING, BacktestStatus.COMPLETED, completed_at=completed_at
        )

    async def mark_failed(
        self, run_id: UUID, failure_code: str, failure_message: str, completed_at: datetime
    ) -> BacktestRun:
        return await self._mark(
            run_id,
            BacktestStatus.RUNNING,
            BacktestStatus.FAILED,
            failure_code=failure_code,
            failure_message=failure_message,
            completed_at=completed_at,
        )


class Executor:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.received: BacktestRun | None = None

    async def execute(self, run: BacktestRun) -> BacktestExecutionResult:
        self.received = run
        if self.failure:
            raise self.failure
        return BacktestExecutionResult()


async def test_success_is_durable_and_preserves_nested_metadata() -> None:
    repository, executor = FakeRepository(), Executor()
    service = BacktestService(repository, executor, clock=lambda: NOW)  # type: ignore[arg-type]
    parameters = {
        "entry": "next_open",
        "risk": {"stop_loss_pct": 5},
        "filters": ["breakout", "volume"],
    }
    run = await service.create(
        " breakout ", " 1.0 ", date(2025, 1, 1), date(2025, 12, 31), parameters, NOW
    )
    assert executor.received and executor.received.status == BacktestStatus.RUNNING
    assert run.status == BacktestStatus.COMPLETED and run.parameters == parameters
    assert run.strategy_version == "1.0" and run.data_as_of == NOW
    assert repository.commits == [
        BacktestStatus.PENDING,
        BacktestStatus.RUNNING,
        BacktestStatus.COMPLETED,
    ]


async def test_executor_failure_is_safe_and_persisted() -> None:
    repository, executor = FakeRepository(), Executor(RuntimeError("database password secret"))
    service = BacktestService(repository, executor, clock=lambda: NOW)  # type: ignore[arg-type]
    with pytest.raises(BacktestExecutionError, match="Backtest execution failed"):
        await service.create("breakout", None, date(2025, 1, 1), date(2025, 2, 1), {}, None)
    assert repository.run and repository.run.status == BacktestStatus.FAILED
    assert repository.run.failure_code == "BACKTEST_EXECUTION_FAILED"
    assert "secret" not in (repository.run.failure_message or "")
    assert repository.commits[-1] == BacktestStatus.FAILED


async def test_invalid_ranges_are_rejected() -> None:
    service = BacktestService(FakeRepository(), Executor(), max_range_days=10)  # type: ignore[arg-type]
    with pytest.raises(InvalidBacktestRangeError):
        await service.create("breakout", None, date(2025, 1, 1), date(2025, 2, 1), {}, None)
