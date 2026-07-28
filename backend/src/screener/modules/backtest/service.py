from datetime import date, datetime
from typing import Any
from uuid import UUID

from screener.modules.backtest.domain import BacktestRun
from screener.modules.backtest.executor import BacktestExecutor
from screener.modules.backtest.repository import BacktestRepository


class BacktestNotFoundError(LookupError):
    pass


class BacktestRangeError(ValueError):
    pass


class BacktestService:
    def __init__(
        self, repository: BacktestRepository, executor: BacktestExecutor, max_range_days: int
    ) -> None:
        self.repository = repository
        self.executor = executor
        self.max_range_days = max_range_days

    async def create(
        self,
        strategy_name: str,
        start_date: date,
        end_date: date,
        strategy_version: str | None = None,
        parameters: dict[str, Any] | None = None,
        data_as_of: datetime | None = None,
    ) -> BacktestRun:
        if (end_date - start_date).days > self.max_range_days:
            raise BacktestRangeError(f"date range cannot exceed {self.max_range_days} days")
        run = BacktestRun.create(
            strategy_name, start_date, end_date, strategy_version, parameters, data_as_of
        )
        await self.repository.save(run)
        running = run.start()
        await self.repository.save(running)
        try:
            execution = await self.executor.execute(running)
        except Exception as exc:
            failed = running.fail(str(exc), type(exc).__name__)
            await self.repository.save(failed)
            return failed
        completed = running.complete(execution.metrics)
        await self.repository.save(completed)
        return completed

    async def get(self, run_id: UUID) -> BacktestRun:
        run = await self.repository.get(run_id)
        if run is None:
            raise BacktestNotFoundError(str(run_id))
        return run

    async def list(self) -> list[BacktestRun]:
        return await self.repository.list()
