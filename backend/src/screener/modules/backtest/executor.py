from dataclasses import dataclass, field
from typing import Any, Protocol

from screener.modules.backtest.domain import BacktestRun


@dataclass(frozen=True, slots=True)
class BacktestExecutionResult:
    metrics: dict[str, Any] = field(default_factory=dict)


class BacktestExecutor(Protocol):
    async def execute(self, run: BacktestRun) -> BacktestExecutionResult: ...


class PlaceholderBacktestExecutor:
    async def execute(self, run: BacktestRun) -> BacktestExecutionResult:
        return BacktestExecutionResult()
