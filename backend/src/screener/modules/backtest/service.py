"""Application-owned durable backtest lifecycle."""

import logging
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from screener.modules.backtest.errors import (
    BacktestExecutionError,
    BacktestNotFoundError,
    InvalidBacktestRangeError,
)
from screener.modules.backtest.executor import BacktestExecutor
from screener.modules.backtest.models import BacktestRun
from screener.modules.backtest.repository import BacktestRepository

logger = logging.getLogger(__name__)
FAILURE_CODE = "BACKTEST_EXECUTION_FAILED"
SAFE_FAILURE_MESSAGE = "Backtest execution failed"


class BacktestService:
    def __init__(
        self,
        repository: BacktestRepository,
        executor: BacktestExecutor,
        max_range_days: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._executor = executor
        self._max_range_days = max_range_days
        self._clock = clock or (lambda: datetime.now(UTC))

    async def create(
        self,
        strategy_name: str,
        strategy_version: str | None,
        start_date: date,
        end_date: date,
        parameters: Mapping[str, Any],
        data_as_of: datetime | None,
    ) -> BacktestRun:
        name = strategy_name.strip()
        version = strategy_version.strip() if strategy_version else None
        if not name:
            raise InvalidBacktestRangeError("strategy_name must not be blank")
        if start_date > end_date:
            raise InvalidBacktestRangeError("start_date must be on or before end_date")
        if (end_date - start_date).days > self._max_range_days:
            raise InvalidBacktestRangeError(
                f"date range must not exceed {self._max_range_days} days"
            )
        pending = await self._repository.create(
            name, version, start_date, end_date, parameters, data_as_of, self._clock()
        )
        await self._repository.commit()
        running = await self._repository.mark_running(pending.id, self._clock())
        await self._repository.commit()
        try:
            await self._executor.execute(running)
        except Exception as exc:
            logger.exception("Backtest executor failed", extra={"backtest_run_id": str(running.id)})
            await self._repository.mark_failed(
                running.id, FAILURE_CODE, SAFE_FAILURE_MESSAGE, self._clock()
            )
            await self._repository.commit()
            raise BacktestExecutionError(SAFE_FAILURE_MESSAGE) from exc
        completed = await self._repository.mark_completed(running.id, self._clock())
        await self._repository.commit()
        return completed

    async def get(self, run_id: UUID) -> BacktestRun:
        run = await self._repository.get(run_id)
        if run is None:
            raise BacktestNotFoundError(f"Backtest run {run_id} was not found")
        return run

    async def list(self, limit: int = 100, offset: int = 0) -> list[BacktestRun]:
        return await self._repository.list(limit, offset)
