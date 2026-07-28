import asyncio
from datetime import date
from typing import cast
from uuid import UUID

import pytest

from screener.modules.backtest import (
    BacktestExecutionResult,
    BacktestRun,
    BacktestService,
    BacktestStatus,
)
from screener.modules.backtest.domain import InvalidBacktestTransition
from screener.modules.backtest.repository import BacktestRepository


class MemoryRepository:
    def __init__(self) -> None:
        self.runs: dict[UUID, BacktestRun] = {}
        self.analysis_reads = 0

    async def save(self, run: BacktestRun) -> BacktestRun:
        self.runs[run.id] = run
        return run

    async def get(self, run_id: UUID) -> BacktestRun | None:
        return self.runs.get(run_id)

    async def list(self) -> list[BacktestRun]:
        return list(self.runs.values())

    async def list_all_trades_for_analysis(self, run_id: UUID):
        self.analysis_reads += 1
        return []

    async def list_portfolio_snapshots(self, run_id: UUID):
        return []


class Executor:
    async def execute(self, run: BacktestRun) -> BacktestExecutionResult:
        return BacktestExecutionResult({"trades": 2})


def test_service_executes_and_completes_run() -> None:
    async def exercise() -> None:
        repository = MemoryRepository()
        service = BacktestService(cast(BacktestRepository, repository), Executor(), 30)
        run = await service.create("watchlist_entry", date(2025, 1, 1), date(2025, 1, 10))
        assert run.status is BacktestStatus.COMPLETED
        assert run.strategy_version == "1"
        assert run.result == {"trades": 2}
        assert await service.get(run.id) == run

    asyncio.run(exercise())


def test_domain_rejects_unguarded_transition() -> None:
    run = BacktestRun.create("watchlist_entry", date(2025, 1, 1), date(2025, 1, 2))
    with pytest.raises(InvalidBacktestTransition):
        run.complete({})


@pytest.mark.parametrize(
    ("name", "version"),
    [("other", None), ("watchlist_entry", "2")],
)
def test_service_rejects_unsupported_strategy_before_persistence(
    name: str, version: str | None
) -> None:
    async def exercise() -> None:
        repository = MemoryRepository()
        service = BacktestService(cast(BacktestRepository, repository), Executor(), 30)
        with pytest.raises(ValueError, match="only strategy_name"):
            await service.create(name, date(2025, 1, 1), date(2025, 1, 10), version)
        assert repository.runs == {}

    asyncio.run(exercise())


def test_service_does_not_read_trades_for_non_completed_analysis() -> None:
    async def exercise() -> None:
        repository = MemoryRepository()
        pending = BacktestRun.create("watchlist_entry", date(2025, 1, 1), date(2025, 1, 2))
        repository.runs[pending.id] = pending
        service = BacktestService(cast(BacktestRepository, repository), Executor(), 30)
        with pytest.raises(RuntimeError, match="available only for completed runs"):
            await service.analyze(pending.id)
        assert repository.analysis_reads == 0

    asyncio.run(exercise())


def test_malformed_completed_portfolio_result_returns_stable_error() -> None:
    async def exercise() -> None:
        repository = MemoryRepository()
        run = (
            BacktestRun.create(
                "watchlist_entry",
                date(2025, 1, 1),
                date(2025, 1, 2),
                parameters={"execution_mode": "portfolio"},
            )
            .start()
            .complete({"initial_capital": "1000.00000000"})
        )
        repository.runs[run.id] = run
        service = BacktestService(cast(BacktestRepository, repository), Executor(), 30)
        with pytest.raises(RuntimeError, match="result is incomplete"):
            await service.portfolio(run.id)

    asyncio.run(exercise())
