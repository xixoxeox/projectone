"""Typed failures at the backtest application boundary."""


class BacktestError(Exception):
    """Base class for expected backtest failures."""


class BacktestNotFoundError(BacktestError):
    pass


class InvalidBacktestRangeError(BacktestError):
    pass


class InvalidBacktestTransitionError(BacktestError):
    pass


class BacktestExecutionError(BacktestError):
    pass
