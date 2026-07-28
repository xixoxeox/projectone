import os
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from screener.modules.backtest import BacktestRepository, BacktestRun
from screener.modules.backtest.models import BacktestRunRecord

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL PostgreSQL database is required"
)


async def test_all_metadata_survives_database_round_trip() -> None:
    url = os.environ["TEST_DATABASE_URL"]
    if not url.startswith("postgresql+asyncpg://"):
        pytest.fail("TEST_DATABASE_URL must use postgresql+asyncpg")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    data_as_of = datetime(2026, 1, 21, 12, 30, tzinfo=UTC)
    original = (
        BacktestRun.create(
            "breakout",
            date(2026, 1, 1),
            date(2026, 1, 20),
            "v2",
            {"lookback": 20, "nested": {"enabled": True}},
            data_as_of,
        )
        .start()
        .fail("provider unavailable", "MARKET_DATA_UNAVAILABLE")
    )
    async with sessions() as session:
        repository = BacktestRepository(session)
        await repository.save(original)
        await session.commit()
    async with sessions() as session:
        restored = await BacktestRepository(session).get(original.id)
        await session.execute(delete(BacktestRunRecord).where(BacktestRunRecord.id == original.id))
        await session.commit()
    assert restored == original
    await engine.dispose()
