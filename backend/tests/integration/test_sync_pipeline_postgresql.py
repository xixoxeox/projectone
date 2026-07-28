import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from screener.config import Settings
from screener.main import should_start_scheduler, sync_conflict_handler
from screener.modules.identity.presentation.dependencies import get_current_user
from screener.modules.market.domain import DailyBar, InstrumentSnapshot
from screener.modules.market.infrastructure.models import DailyBarRecord, Stock, SyncJobRun
from screener.modules.market.infrastructure.repositories import DailyBarRepository, StockRepository
from screener.modules.market.presentation.admin_router import coordinator, router
from screener.modules.market.scheduler import build_scheduler
from screener.modules.market.sync import (
    DailyBarSyncService,
    StockSyncService,
    SyncAlreadyRunningError,
    SyncResult,
)


class OfflineProvider:
    def __init__(self) -> None:
        self.requests: list[tuple[str, date, date]] = []
        self.release = asyncio.Event()
        self.failure: Exception | None = None
        self.future_bar = False

    async def stock_master(self, market: str = "KOSPI") -> list[InstrumentSnapshot]:
        await self.release.wait()
        if self.failure is not None:
            raise self.failure
        return []

    async def daily_bars(self, symbol: str, start: date, end: date) -> list[DailyBar]:
        self.requests.append((symbol, start, end))
        if self.future_bar:
            return [bar(trading_date=end + timedelta(days=1))]
        return []


def snapshot(name: str = "Samsung") -> InstrumentSnapshot:
    return InstrumentSnapshot(
        symbol="005930",
        name=name,
        market="KOSPI",
        exchange="KRX",
        currency="KRW",
        country="KR",
        security_type="stock",
        listing_status="listed",
        source="offline",
        as_of=datetime.now(UTC),
    )


def bar(close: str = "11", trading_date: date = date(2026, 1, 2)) -> DailyBar:
    return DailyBar(
        symbol="005930",
        trading_date=trading_date,
        open=Decimal("10"),
        high=Decimal("12"),
        low=Decimal("9"),
        close=Decimal(close),
        volume=100,
        source="offline",
        as_of=datetime(2026, 1, 2, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_repository_upsert_insert_update_and_skip(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        stocks = StockRepository(session)
        assert (await stocks.upsert([snapshot()])).inserted == 1
        await session.commit()
        assert (await stocks.upsert([snapshot()])).skipped == 1
        assert (await stocks.upsert([snapshot("Samsung Electronics")])).updated == 1
        await session.commit()

        bars = DailyBarRepository(session)
        assert (await bars.upsert([bar()])).inserted == 1
        await session.commit()
        assert (await bars.upsert([bar()])).skipped == 1
        assert (await bars.upsert([bar("10.5")])).updated == 1
        await session.commit()
        session.expire_all()
        stored = await session.get(Stock, "005930")
        assert stored is not None and stored.name == "Samsung Electronics"


@pytest.mark.asyncio
async def test_daily_bar_duplicate_is_rejected_before_database_io() -> None:
    session = AsyncMock(spec=AsyncSession)
    with pytest.raises(ValueError, match="duplicate trading dates"):
        await DailyBarRepository(session).upsert([bar(), bar()])
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_symbol_latest_dates_does_not_query() -> None:
    session = AsyncMock(spec=AsyncSession)
    assert await DailyBarRepository(session).latest_dates([]) == {}
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_incremental_sync_bootstrap_and_latest_date(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    provider = OfflineProvider()
    async with postgres_session_factory() as session:
        session.add_all(
            [
                Stock(symbol="000001", name="New", market="KOSPI", currency="KRW", country="KR"),
                Stock(
                    symbol="000002", name="Existing", market="KOSPI", currency="KRW", country="KR"
                ),
            ]
        )
        await session.flush()
        session.add(
            DailyBarRecord(
                symbol="000002",
                trading_date=date.today() - timedelta(days=2),
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
                source="offline",
            )
        )
        await session.commit()
        service = DailyBarSyncService(postgres_session_factory, provider, history_years=3)
        await service._sync(session)
    requests_by_symbol: dict[str, list[tuple[date, date]]] = {}
    for symbol, start, end in provider.requests:
        requests_by_symbol.setdefault(symbol, []).append((start, end))

    expected_starts = {
        "000001": date.today() - timedelta(days=365 * 3),
        "000002": date.today() - timedelta(days=1),
    }
    for symbol, expected_start in expected_starts.items():
        windows = sorted(requests_by_symbol[symbol])
        assert windows[0][0] == expected_start
        assert windows[-1][1] == date.today()
        assert all(start <= end for start, end in windows)
        assert all(
            next_start == current_end + timedelta(days=1)
            for (_, current_end), (next_start, _) in zip(windows, windows[1:], strict=False)
        )


def test_daily_bar_validation_rejects_negative_and_invalid_ohlc() -> None:
    with pytest.raises(ValidationError):
        DailyBar(
            symbol="005930",
            trading_date=date.today(),
            open=10,
            high=9,
            low=8,
            close=10,
            volume=-1,
            source="offline",
            as_of=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_sync_rejects_future_trading_dates(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    provider = OfflineProvider()
    provider.future_bar = True
    async with postgres_session_factory() as session:
        session.add(
            Stock(symbol="005930", name="Samsung", market="KOSPI", currency="KRW", country="KR")
        )
        await session.commit()
        with pytest.raises(ValueError, match="future trading date"):
            await DailyBarSyncService(postgres_session_factory, provider)._sync(session)


@pytest.mark.asyncio
async def test_sync_records_success_and_failure(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    provider = OfflineProvider()
    provider.release.set()
    successful = StockSyncService(postgres_session_factory, provider)
    assert (await successful.run()).status == "succeeded"
    provider.failure = RuntimeError("offline failure")
    failing = StockSyncService(postgres_session_factory, provider)
    with pytest.raises(RuntimeError, match="offline failure"):
        await failing.run()
    assert not failing._run_lock.locked()
    async with postgres_session_factory() as session:
        statuses = [
            run.status
            for run in (await session.scalars(select(SyncJobRun).order_by(SyncJobRun.id))).all()
        ]
    assert statuses == ["succeeded", "failed"]


@pytest.mark.asyncio
async def test_same_job_cannot_run_concurrently(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    provider = OfflineProvider()
    service = StockSyncService(postgres_session_factory, provider)
    first = asyncio.create_task(service.run())
    await asyncio.sleep(0)
    with pytest.raises(SyncAlreadyRunningError):
        await service.run()
    provider.release.set()
    await first
    assert not service._run_lock.locked()


def test_scheduler_registration_and_test_environment_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = build_scheduler(Mock(), Mock())
    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert set(jobs) == {"stock_master", "daily_bars"}
    assert all(job.coalesce and job.max_instances == 1 for job in jobs.values())
    assert not scheduler.running
    monkeypatch.setattr("screener.main.settings", Settings(app_env="test"))
    assert not should_start_scheduler()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/admin/sync/stocks"),
        ("post", "/api/v1/admin/sync/daily-bars"),
        ("post", "/api/v1/admin/sync/all"),
        ("get", "/api/v1/admin/sync/status"),
        ("get", "/api/v1/admin/sync/history"),
    ],
)
def test_every_admin_sync_api_rejects_unauthenticated_and_non_admin_users(
    method: str, path: str
) -> None:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    with TestClient(test_app) as client:
        assert client.request(method, path).status_code == 401
        test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="user")
        assert client.request(method, path).status_code == 403


def test_admin_can_execute_sync() -> None:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    result = SyncResult(
        job_name="stock_master",
        status="succeeded",
        inserted_rows=1,
        updated_rows=0,
        skipped_rows=0,
        duration_ms=1,
    )
    stock_service = SimpleNamespace(run=AsyncMock(return_value=result))
    value = SimpleNamespace(stocks=stock_service)
    test_app.dependency_overrides[coordinator] = lambda: value
    with TestClient(test_app) as client:
        assert client.post("/api/v1/admin/sync/stocks").status_code == 401
        test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="user")
        assert client.post("/api/v1/admin/sync/stocks").status_code == 403
        test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
        response = client.post("/api/v1/admin/sync/stocks")
    assert response.status_code == 200
    assert response.json()["job_name"] == "stock_master"


def test_concurrent_admin_sync_returns_conflict() -> None:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    test_app.add_exception_handler(SyncAlreadyRunningError, sync_conflict_handler)
    stock_service = SimpleNamespace(
        run=AsyncMock(side_effect=SyncAlreadyRunningError("stock_master"))
    )
    test_app.dependency_overrides[coordinator] = lambda: SimpleNamespace(stocks=stock_service)
    test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
    with TestClient(test_app) as client:
        response = client.post("/api/v1/admin/sync/stocks")
    assert response.status_code == 409
    assert response.json()["job_name"] == "stock_master"
