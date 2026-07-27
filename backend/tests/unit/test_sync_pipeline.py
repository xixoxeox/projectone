from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from screener.modules.market.domain import DailyBar
from screener.modules.market.infrastructure.repositories import DailyBarRepository
from screener.modules.market.scheduler import build_scheduler


def test_scheduler_registers_two_coalesced_singleton_jobs() -> None:
    scheduler = build_scheduler(Mock(), Mock())
    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert set(jobs) == {"stock_master", "daily_bars"}
    assert all(job.coalesce and job.max_instances == 1 for job in jobs.values())
    assert not scheduler.running


def test_daily_bar_rejects_negative_and_invalid_ohlc() -> None:
    with pytest.raises(ValidationError):
        DailyBar(
            symbol="005930",
            trading_date=date.today(),
            open=Decimal("10"),
            high=Decimal("9"),
            low=Decimal("8"),
            close=Decimal("10"),
            volume=-1,
            source="test",
            as_of=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_repository_rejects_duplicate_dates_before_database_io() -> None:
    session = AsyncMock()
    bar = DailyBar(
        symbol="005930",
        trading_date=date(2026, 1, 2),
        open=Decimal("10"),
        high=Decimal("12"),
        low=Decimal("9"),
        close=Decimal("11"),
        volume=100,
        source="test",
        as_of=datetime(2026, 1, 2, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="duplicate trading dates"):
        await DailyBarRepository(session).upsert([bar, bar])
    session.execute.assert_not_awaited()
