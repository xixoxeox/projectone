import builtins
from datetime import date, datetime
from typing import Any
from uuid import UUID

from screener.modules.backtest.analysis import BacktestAnalysis, analyze_backtest_trades
from screener.modules.backtest.domain import (
    BacktestExitReason,
    BacktestRun,
    BacktestStatus,
    BacktestTrade,
)
from screener.modules.backtest.executor import (
    BacktestExecutionError,
    BacktestExecutor,
    validate_strategy_contract,
)
from screener.modules.backtest.repository import BacktestRepository


class BacktestNotFoundError(LookupError):
    pass


class BacktestRangeError(ValueError):
    pass


class BacktestAnalysisUnavailableError(RuntimeError):
    pass


class PortfolioUnavailableError(RuntimeError):
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
        strategy_name, strategy_version = validate_strategy_contract(
            strategy_name, strategy_version
        )
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

    async def analyze(self, run_id: UUID) -> BacktestAnalysis:
        run = await self.get(run_id)
        if run.status is not BacktestStatus.COMPLETED:
            raise BacktestAnalysisUnavailableError(
                "Backtest analysis is available only for completed runs"
            )
        trades = await self.repository.list_all_trades_for_analysis(run_id)
        return analyze_backtest_trades(run_id, trades)

    async def portfolio(self, run_id: UUID) -> tuple[BacktestRun, builtins.list[Any]]:
        run = await self.get(run_id)
        if run.status is not BacktestStatus.COMPLETED:
            raise PortfolioUnavailableError("Portfolio data is available only for completed runs")
        if run.execution_mode.value != "portfolio":
            raise PortfolioUnavailableError("Portfolio data is unavailable for independent runs")
        return run, await self.repository.list_portfolio_snapshots(run_id)
