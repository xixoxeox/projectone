"""Backtest lifecycle and persistence foundation."""

from screener.modules.backtest.errors import (
    BacktestExecutionError,
    BacktestNotFoundError,
    InvalidBacktestRangeError,
    InvalidBacktestTransitionError,
)
from screener.modules.backtest.executor import (
    BacktestExecutionResult,
    BacktestExecutor,
    PlaceholderBacktestExecutor,
)
from screener.modules.backtest.models import BacktestRun, BacktestStatus
from screener.modules.backtest.repository import BacktestRepository
from screener.modules.backtest.service import BacktestService

__all__ = [
    "BacktestExecutionError",
    "BacktestExecutionResult",
    "BacktestExecutor",
    "BacktestNotFoundError",
    "BacktestRepository",
    "BacktestRun",
    "BacktestService",
    "BacktestStatus",
    "InvalidBacktestRangeError",
    "InvalidBacktestTransitionError",
    "PlaceholderBacktestExecutor",
]
