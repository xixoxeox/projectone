"""Dependency providers for the watchlist API."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.market.watchlist import WatchlistRepository
from screener.shared.database import get_db_session


def get_watchlist_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WatchlistRepository:
    """Build a repository around the request-scoped database session."""
    return WatchlistRepository(session)


WatchlistRepositoryDependency = Annotated[WatchlistRepository, Depends(get_watchlist_repository)]
