"""Tests for the intentionally small backtest lifecycle service."""

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest

from screener.modules.backtest import (
    BacktestRun,
    BacktestService,
    BacktestStatus,
    InvalidBacktestTransition,
)

NOW = datetime(2026, 7, 28, 12, tzinfo=UTC)


class FakeRepository:
    def __init__(self) -> None:
        self.run: BacktestRun | None = None

    async def create(
        self,
        strategy_name: str,
        start_date: date,
        end_date: date,
        parameters: dict[str, Any],
        created_at: datetime,
    ) -> BacktestRun:
        self.run = BacktestRun(
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            parameters=parameters,
            created_at=created_at,
        )
        return self.run

    async def get(self, run_id: UUID) -> BacktestRun | None:
        return self.run if self.run and self.run.id == run_id else None

    async def list(self, limit: int = 100, offset: int = 0) -> list[BacktestRun]:
        return [self.run] if self.run else []

    async def update_status(
        self, run_id: UUID, status: BacktestStatus, **changes: Any
    ) -> BacktestRun | None:
        if not self.run or self.run.id != run_id:
            return None
        self.run = self.run.model_copy(update={"status": status, **changes})
        return self.run


@pytest.fixture
def repository() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def service(repository: FakeRepository) -> BacktestService:
    return BacktestService(repository, clock=lambda: NOW)  # type: ignore[arg-type]


async def test_create_only_persists_pending_metadata(
    service: BacktestService,
) -> None:
    run = await service.create(" breakout ", date(2025, 1, 1), date(2025, 12, 31), {"window": 20})
    assert run.strategy_name == "breakout"
    assert run.status == BacktestStatus.PENDING
    assert run.started_at is None
    assert run.completed_at is None
    assert run.created_at == NOW


async def test_rejects_inverted_date_range(service: BacktestService) -> None:
    with pytest.raises(ValueError, match="start_date"):
        await service.create("breakout", date(2025, 2, 1), date(2025, 1, 1), {})


async def test_lifecycle_transitions_preserve_timestamps(
    service: BacktestService,
) -> None:
    pending = await service.create("breakout", date(2025, 1, 1), date(2025, 2, 1), {})
    running = await service.mark_running(pending.id)
    assert running and running.status == BacktestStatus.RUNNING and running.started_at == NOW
    completed = await service.mark_completed(pending.id)
    assert completed and completed.status == BacktestStatus.COMPLETED
    assert completed.started_at == NOW and completed.completed_at == NOW


async def test_invalid_transition_is_rejected(service: BacktestService) -> None:
    pending = await service.create("breakout", date(2025, 1, 1), date(2025, 2, 1), {})
    with pytest.raises(InvalidBacktestTransition):
        await service.mark_completed(pending.id)
