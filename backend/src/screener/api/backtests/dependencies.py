"""Dependency providers for the backtest API."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.backtest import BacktestRepository, BacktestService
from screener.shared.database import get_db_session


def get_backtest_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BacktestService:
    return BacktestService(BacktestRepository(session))


BacktestServiceDependency = Annotated[BacktestService, Depends(get_backtest_service)]
