from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from screener.config import get_settings
from screener.modules.backtest import (
    BacktestRepository,
    BacktestService,
    DatabaseBacktestExecutor,
    WatchlistEntryStrategy,
)
from screener.shared.database import get_db_session


def get_backtest_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BacktestService:
    return BacktestService(
        BacktestRepository(session),
        DatabaseBacktestExecutor(session, WatchlistEntryStrategy(session)),
        get_settings().backtest_max_range_days,
    )


BacktestServiceDependency = Annotated[BacktestService, Depends(get_backtest_service)]
