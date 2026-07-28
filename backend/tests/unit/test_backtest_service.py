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

    async def save(self, run: BacktestRun) -> BacktestRun:
        self.runs[run.id] = run
        return run

    async def get(self, run_id: UUID) -> BacktestRun | None:
        return self.runs.get(run_id)

    async def list(self) -> list[BacktestRun]:
        return list(self.runs.values())


class Executor:
    async def execute(self, run: BacktestRun) -> BacktestExecutionResult:
        return BacktestExecutionResult({"trades": 2})


def test_service_executes_and_completes_run() -> None:
    async def exercise() -> None:
        repository = MemoryRepository()
        service = BacktestService(cast(BacktestRepository, repository), Executor(), 30)
        run = await service.create("breakout", date(2025, 1, 1), date(2025, 1, 10))
        assert run.status is BacktestStatus.COMPLETED
        assert run.result == {"trades": 2}
        assert await service.get(run.id) == run

    asyncio.run(exercise())


def test_domain_rejects_unguarded_transition() -> None:
    run = BacktestRun.create("breakout", date(2025, 1, 1), date(2025, 1, 2))
    with pytest.raises(InvalidBacktestTransition):
        run.complete({})
