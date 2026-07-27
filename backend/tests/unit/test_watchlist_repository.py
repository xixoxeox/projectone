"""Unit tests for SQLAlchemy watchlist persistence."""

from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from screener.modules.market.ranking import RankedCandidate
from screener.modules.market.screening import ScreeningResult
from screener.modules.market.watchlist import WatchlistRepository
from screener.shared.database import Base


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


def candidate(
    symbol: str, rank: int, score: str = "91.12345678901234567890123456789"
) -> RankedCandidate:
    snapshot = ScreeningResult(
        symbol=symbol,
        passed=True,
        reasons=["PASSED: deterministic test"],
        warnings=["screen warning"],
        metrics={"precise": Decimal("0.12345678901234567890123456789")},
    )
    return RankedCandidate(
        symbol=symbol,
        rank=rank,
        total_score=Decimal(score),
        component_scores={"trend": Decimal("87.12345678901234567890123456789")},
        source_result=snapshot,
        warnings=["ranking warning"],
    )


async def test_save_one_day_orders_entries_and_exists(session: AsyncSession) -> None:
    repository = WatchlistRepository(session)
    day = date(2026, 7, 24)
    await repository.save(day, [candidate("BBB", 2), candidate("AAA", 1)])

    assert [entry.symbol for entry in await repository.list(day)] == ["AAA", "BBB"]
    assert await repository.exists(day)
    assert not await repository.exists(date(2026, 7, 23))


async def test_multiple_days_latest_and_delete_are_date_scoped(session: AsyncSession) -> None:
    repository = WatchlistRepository(session)
    older = date(2026, 7, 23)
    newer = date(2026, 7, 24)
    await repository.save(newer, [candidate("NEW", 1)])
    await repository.save(older, [candidate("OLD", 1)])

    assert [entry.symbol for entry in await repository.latest()] == ["NEW"]
    await repository.delete(older)
    assert await repository.list(older) == []
    assert [entry.symbol for entry in await repository.list(newer)] == ["NEW"]


async def test_latest_is_empty_when_repository_is_empty(session: AsyncSession) -> None:
    assert await WatchlistRepository(session).latest() == []


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ([candidate("AAA", 1), candidate("AAA", 2)], "duplicate symbol"),
        ([candidate("AAA", 1), candidate("BBB", 1)], "duplicate rank"),
        ([candidate("   ", 1)], "must not be blank"),
    ],
)
async def test_invalid_candidates_are_rejected_before_writing(
    session: AsyncSession, values: list[RankedCandidate], message: str
) -> None:
    repository = WatchlistRepository(session)
    with pytest.raises(ValueError, match=message):
        await repository.save(date(2026, 7, 24), values)
    assert await repository.latest() == []


async def test_empty_trading_date_is_rejected(session: AsyncSession) -> None:
    repository = WatchlistRepository(session)
    with pytest.raises(ValueError, match="trading_date"):
        await repository.save(None, [])  # type: ignore[arg-type]


async def test_snapshot_and_all_decimals_preserve_precision(session: AsyncSession) -> None:
    repository = WatchlistRepository(session)
    original = candidate("AAA", 1)
    await repository.save(date(2026, 7, 24), [original])
    saved = (await repository.latest())[0]

    assert saved.total_score == original.total_score
    assert saved.component_scores == original.component_scores
    assert saved.snapshot == original.source_result
    assert saved.snapshot.metrics == original.source_result.metrics
    assert saved.snapshot is not original.source_result


async def test_failed_save_rolls_back_delete_and_partial_insert(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = WatchlistRepository(session)
    day = date(2026, 7, 24)
    await repository.save(day, [candidate("ORIGINAL", 1)])
    original_flush = session.flush

    async def fail_after_flush() -> None:
        await original_flush()
        raise RuntimeError("injected halfway failure")

    monkeypatch.setattr(session, "flush", fail_after_flush)
    with pytest.raises(RuntimeError, match="injected halfway failure"):
        await repository.save(day, [candidate("AAA", 1), candidate("BBB", 2)])
    monkeypatch.setattr(session, "flush", original_flush)

    assert [entry.symbol for entry in await repository.list(day)] == ["ORIGINAL"]


async def test_save_does_not_mutate_candidate_and_replaces_same_date(
    session: AsyncSession,
) -> None:
    repository = WatchlistRepository(session)
    day = date(2026, 7, 24)
    original = candidate("AAA", 1)
    before = original.model_copy(deep=True)
    await repository.save(day, [original])
    await repository.save(day, [candidate("REPLACEMENT", 1)])

    assert original == before
    assert [entry.symbol for entry in await repository.list(day)] == ["REPLACEMENT"]
