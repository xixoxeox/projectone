from dataclasses import dataclass
from typing import Any, Protocol

from screener.modules.backtest.domain import BacktestRun


@dataclass(frozen=True, slots=True)
class BacktestExecutionResult:
    metrics: dict[str, Any]


class BacktestExecutor(Protocol):
    async def execute(self, run: BacktestRun) -> BacktestExecutionResult: ...


class PlaceholderBacktestExecutor:
    async def execute(self, run: BacktestRun) -> BacktestExecutionResult:
        return BacktestExecutionResult(
            metrics={"strategy_name": run.strategy_name, "trades": 0, "total_return": 0.0}
        )
