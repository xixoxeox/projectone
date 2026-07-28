"""PostgreSQL-only verification of the backtest persistence contract."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from screener.config import get_settings
from screener.modules.backtest import (
    BacktestExecutionError,
    BacktestExecutionResult,
    BacktestNotFoundError,
    BacktestRepository,
    BacktestService,
    BacktestStatus,
    InvalidBacktestTransitionError,
)

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 7, 28, 12, 30, tzinfo=UTC)
PARAMETERS = {
    "entry": "next_open",
    "risk": {"stop_loss_pct": 5, "take_profit_pct": 12},
    "filters": ["breakout", "volume"],
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    value = create_async_engine(get_settings().database_url)
    yield value
    await value.dispose()


@pytest.fixture
async def sessions(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE backtest_runs"))
    yield async_sessionmaker(engine, expire_on_commit=False)


async def create_pending(repository: BacktestRepository) -> UUID:
    run = await repository.create(
        "breakout", "1.0", date(2025, 1, 1), date(2025, 12, 31), PARAMETERS, NOW, NOW
    )
    await repository.commit()
    return run.id


async def test_postgresql_schema_and_jsonb_round_trip(
    engine: AsyncEngine, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        repository = BacktestRepository(session)
        run_id = await create_pending(repository)
    async with sessions() as session:
        run = await BacktestRepository(session).get(run_id)
        assert run is not None
        assert run.parameters == PARAMETERS
        assert run.strategy_version == "1.0"
        assert run.data_as_of == NOW
        assert isinstance(run.id, UUID)
        assert run.data_as_of.utcoffset() == UTC.utcoffset(NOW)

    async with engine.connect() as connection:
        columns = await connection.run_sync(
            lambda sync: {
                column["name"]: str(column["type"])
                for column in inspect(sync).get_columns("backtest_runs")
            }
        )
        indexes = await connection.run_sync(
            lambda sync: {index["name"] for index in inspect(sync).get_indexes("backtest_runs")}
        )
        enum_labels = (
            (
                await connection.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_type.oid = enumtypid "
                        "WHERE typname = 'backtest_status' ORDER BY enumsortorder"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert columns["parameters"] == "JSONB"
    assert columns["id"] == "UUID"
    assert enum_labels == ["pending", "running", "completed", "failed"]
    assert {
        "ix_backtest_runs_status",
        "ix_backtest_runs_created_at",
        "ix_backtest_runs_strategy_name",
    } <= indexes


async def test_check_constraint_rejects_inverted_range(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        repository = BacktestRepository(session)
        with pytest.raises(IntegrityError):
            await repository.create(
                "breakout", None, date(2025, 2, 1), date(2025, 1, 1), {}, None, NOW
            )


async def test_atomic_concurrent_transition_and_terminal_guards(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        run_id = await create_pending(BacktestRepository(session))

    async def mark_running() -> object:
        async with sessions() as session:
            repository = BacktestRepository(session)
            try:
                result = await repository.mark_running(run_id, NOW)
                await repository.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(mark_running(), mark_running())
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, InvalidBacktestTransitionError) for result in results) == 1

    async with sessions() as session:
        repository = BacktestRepository(session)
        completed = await repository.mark_completed(run_id, NOW)
        await repository.commit()
        assert completed.status == BacktestStatus.COMPLETED
        with pytest.raises(InvalidBacktestTransitionError):
            await repository.mark_running(run_id, NOW)
        with pytest.raises(InvalidBacktestTransitionError):
            await repository.mark_failed(run_id, "CODE", "safe", NOW)
        with pytest.raises(BacktestNotFoundError):
            await repository.mark_running(uuid4(), NOW)

    async with sessions() as session:
        failed_id = await create_pending(BacktestRepository(session))
    async with sessions() as session:
        repository = BacktestRepository(session)
        await repository.mark_running(failed_id, NOW)
        await repository.commit()
        failed = await repository.mark_failed(failed_id, "CODE", "safe", NOW)
        await repository.commit()
        assert failed.status == BacktestStatus.FAILED


class FailingExecutor:
    async def execute(self, run: object) -> BacktestExecutionResult:
        raise RuntimeError("database password = abc123")


async def test_executor_failure_is_durable_and_sanitized(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        service = BacktestService(
            BacktestRepository(session), FailingExecutor(), max_range_days=1825
        )  # type: ignore[arg-type]
        with pytest.raises(BacktestExecutionError, match="Backtest execution failed"):
            await service.create(
                "breakout", None, date(2025, 1, 1), date(2025, 2, 1), PARAMETERS, NOW
            )
    async with sessions() as session:
        runs = await BacktestRepository(session).list()
        assert len(runs) == 1
        assert runs[0].status == BacktestStatus.FAILED
        assert runs[0].failure_code == "BACKTEST_EXECUTION_FAILED"
        assert runs[0].failure_message == "Backtest execution failed"
        assert "abc123" not in runs[0].failure_message


def test_migration_upgrade_downgrade_and_reupgrade() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.downgrade(config, "-1")

    async def enum_exists() -> bool:
        engine = create_async_engine(get_settings().database_url)
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'backtest_status')")
            )
        await engine.dispose()
        return bool(exists)

    assert not asyncio.run(enum_exists())
    command.upgrade(config, "head")
