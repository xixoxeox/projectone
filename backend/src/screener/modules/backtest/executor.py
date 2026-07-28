"""Execution boundary that PR #20 can extend without changing the lifecycle."""

from dataclasses import dataclass
from typing import Protocol

from screener.modules.backtest.models import BacktestRun


@dataclass(frozen=True)
class BacktestExecutionResult:
    """Intentionally empty foundation result."""


class BacktestExecutor(Protocol):
    async def execute(self, run: BacktestRun) -> BacktestExecutionResult: ...


class PlaceholderBacktestExecutor:
    """Validate the execution boundary without simulating any trade."""

    async def execute(self, run: BacktestRun) -> BacktestExecutionResult:
        return BacktestExecutionResult()
