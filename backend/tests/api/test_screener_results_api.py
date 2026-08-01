import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from screener.api.screener import router
from screener.modules.identity.presentation.dependencies import get_current_user
from screener.modules.market.infrastructure.models import WatchlistPipelineExecution
from screener.modules.market.screening.swing import SwingScreeningConfig
from screener.shared.database import Base, get_db_session


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    day = date(2026, 7, 31)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add(
                WatchlistPipelineExecution(
                    trading_date=day,
                    trigger_type="manual",
                    status="succeeded",
                    stage="completed",
                    started_at=datetime.now(UTC),
                    finished_at=datetime.now(UTC),
                    screened_count=807,
                    candidate_count=12,
                    qualified_count=0,
                    score_threshold=Decimal("80"),
                    persisted_count=0,
                )
            )
            await session.commit()

    async def session_override() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    asyncio.run(prepare())
    app = FastAPI()
    app.state.swing_screening_config = SwingScreeningConfig()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
    app.dependency_overrides[get_db_session] = session_override
    with TestClient(app) as value:
        yield value
    asyncio.run(engine.dispose())


def test_empty_result_includes_screening_funnel_and_threshold(client: TestClient) -> None:
    response = client.get("/api/v1/screener/results/2026-07-31")

    assert response.status_code == 200
    assert response.json() == {
        "execution_id": response.json()["execution_id"],
        "trading_date": "2026-07-31",
        "screened_count": 807,
        "setup_passed_count": 12,
        "score_qualified_count": 0,
        "score_threshold": "80.00",
        "result_count": 0,
        "items": [],
    }


def test_missing_result_date_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/screener/results/2026-07-30")

    assert response.status_code == 404
