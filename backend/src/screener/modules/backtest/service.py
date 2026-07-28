"""Application service for backtest request and lifecycle management."""

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from screener.modules.backtest.models import BacktestRun, BacktestStatus
from screener.modules.backtest.repository import BacktestRepository


class InvalidBacktestTransition(ValueError):
    """Raised when a lifecycle update does not follow the supported state machine."""


class BacktestService:
    def __init__(
        self, repository: BacktestRepository, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    async def create(
        self, strategy_name: str, start_date: date, end_date: date, parameters: Mapping[str, Any]
    ) -> BacktestRun:
        name = strategy_name.strip()
        if not name:
            raise ValueError("strategy_name must not be blank")
        if start_date > end_date:
            raise ValueError("start_date must be on or before end_date")
        return await self._repository.create(name, start_date, end_date, parameters, self._clock())

    async def get(self, run_id: UUID) -> BacktestRun | None:
        return await self._repository.get(run_id)

    async def list(self, limit: int = 100, offset: int = 0) -> list[BacktestRun]:
        return await self._repository.list(limit, offset)

    async def mark_running(self, run_id: UUID) -> BacktestRun | None:
        run = await self._require_status(run_id, BacktestStatus.PENDING)
        if run is None:
            return None
        return await self._repository.update_status(
            run_id, BacktestStatus.RUNNING, started_at=self._clock()
        )

    async def mark_completed(self, run_id: UUID) -> BacktestRun | None:
        run = await self._require_status(run_id, BacktestStatus.RUNNING)
        if run is None:
            return None
        return await self._repository.update_status(
            run_id,
            BacktestStatus.COMPLETED,
            started_at=run.started_at,
            completed_at=self._clock(),
        )

    async def mark_failed(self, run_id: UUID, error_message: str) -> BacktestRun | None:
        run = await self._require_status(run_id, BacktestStatus.RUNNING)
        if run is None:
            return None
        message = error_message.strip()
        if not message:
            raise ValueError("error_message must not be blank")
        return await self._repository.update_status(
            run_id,
            BacktestStatus.FAILED,
            started_at=run.started_at,
            completed_at=self._clock(),
            error_message=message,
        )

    async def _require_status(self, run_id: UUID, expected: BacktestStatus) -> BacktestRun | None:
        run = await self._repository.get(run_id)
        if run is not None and run.status != expected:
            raise InvalidBacktestTransition(f"cannot transition from {run.status.value}")
        return run
