import builtins
from datetime import date, datetime
from typing import Any
from uuid import UUID

from screener.modules.backtest.domain import BacktestExitReason, BacktestRun, BacktestTrade
from screener.modules.backtest.executor import (
    BacktestExecutionError,
    BacktestExecutor,
    BacktestParameters,
    UnsupportedBacktestStrategy,
)
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
        if strategy_name.strip() != "watchlist_entry" or (
            strategy_version is not None and strategy_version.strip() not in ("", "1")
        ):
            raise UnsupportedBacktestStrategy(
                f"unsupported strategy: {strategy_name.strip()} version {strategy_version!r}"
            )
        BacktestParameters.parse(parameters)
        run = BacktestRun.create(
            strategy_name, start_date, end_date, strategy_version, parameters, data_as_of
        )
        await self.repository.save(run)
        running = run.start()
        await self.repository.save(running)
        try:
            # A savepoint keeps a trade flush failure from poisoning the transaction,
            # allowing the same session to persist the failed lifecycle state.
            async with self.repository.session.begin_nested():
                execution = await self.executor.execute(running)
        except Exception as exc:
            code = (
                exc.failure_code if isinstance(exc, BacktestExecutionError) else "EXECUTION_FAILED"
            )
            failed = running.fail(str(exc), code)
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

    async def list_trades(
        self,
        run_id: UUID,
        limit: int,
        offset: int,
        symbol: str | None,
        exit_reason: BacktestExitReason | None,
    ) -> builtins.list[BacktestTrade]:
        await self.get(run_id)
        return await self.repository.list_trades(run_id, limit, offset, symbol, exit_reason)
