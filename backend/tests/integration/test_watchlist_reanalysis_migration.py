"""PostgreSQL coverage for the intentionally guarded reanalysis downgrade."""

import asyncio
import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from screener.modules.market.infrastructure.models import WatchlistPipelineExecution

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL PostgreSQL database is required"
)


def alembic_config() -> Config:
    return Config(str(Path(__file__).parents[2] / "alembic.ini"))


async def migrate(revision: str) -> None:
    await asyncio.to_thread(
        command.upgrade if revision == "head" else command.downgrade, alembic_config(), revision
    )


@pytest.fixture
async def sessions() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(delete(WatchlistPipelineExecution))
        await session.commit()
    yield factory
    await migrate("head")
    async with factory() as session:
        await session.execute(delete(WatchlistPipelineExecution))
        await session.commit()
    await engine.dispose()


async def test_upgrade_downgrade_upgrade_on_fresh_database(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await migrate("-1")
    await migrate("head")
    async with sessions() as session:
        assert await session.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0008_watchlist_reanalysis"
        )


async def test_downgrade_refuses_without_changing_index_or_history(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    day = date(2026, 7, 31)
    async with sessions() as session:
        session.add_all(
            [
                WatchlistPipelineExecution(
                    trading_date=day,
                    trigger_type="manual",
                    status="succeeded",
                    stage="completed",
                    started_at=datetime(2026, 7, 31, tzinfo=UTC),
                ),
                WatchlistPipelineExecution(
                    trading_date=day,
                    trigger_type="manual_reanalysis",
                    status="succeeded",
                    stage="completed",
                    started_at=datetime(2026, 7, 31, 1, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()

    with pytest.raises(RuntimeError, match="preserved reanalysis audit history"):
        await migrate("-1")

    async with sessions() as session:
        rows = list(
            (
                await session.scalars(
                    select(WatchlistPipelineExecution).where(
                        WatchlistPipelineExecution.trading_date == day
                    )
                )
            ).all()
        )
        index_exists = await session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_indexes "
                "WHERE indexname = 'uq_watchlist_pipeline_running_date')"
            )
        )
        version = await session.scalar(text("SELECT version_num FROM alembic_version"))
    assert len(rows) == 2
    assert all(row.status == "succeeded" for row in rows)
    assert index_exists is True
    assert version == "0008_watchlist_reanalysis"
