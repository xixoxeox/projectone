"""Shared test infrastructure for production-database repository tests."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from screener.config import get_settings


@pytest.fixture
async def postgres_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Provide isolated sessions backed by PostgreSQL and an outer rollback."""

    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        factory = async_sessionmaker(
            connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        yield factory
        if transaction.is_active:
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def postgres_session(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with postgres_session_factory() as session:
        yield session
