"""PostgreSQL persistence with atomic, guarded lifecycle transitions."""

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.backtest.errors import (
    BacktestNotFoundError,
    InvalidBacktestTransitionError,
)
from screener.modules.backtest.models import BacktestRun, BacktestRunRecord, BacktestStatus


class BacktestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def create(
        self,
        strategy_name: str,
        strategy_version: str | None,
        start_date: date,
        end_date: date,
        parameters: Mapping[str, Any],
        data_as_of: datetime | None,
        created_at: datetime,
    ) -> BacktestRun:
        record = BacktestRunRecord(
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            start_date=start_date,
            end_date=end_date,
            parameters=dict(parameters),
            data_as_of=data_as_of,
            status=BacktestStatus.PENDING,
            created_at=created_at,
        )
        self._session.add(record)
        await self._session.flush()
        return self._run(record)

    async def get(self, run_id: UUID) -> BacktestRun | None:
        record = await self._session.get(BacktestRunRecord, run_id)
        return None if record is None else self._run(record)

    async def list(self, limit: int = 100, offset: int = 0) -> list[BacktestRun]:
        records = await self._session.scalars(
            select(BacktestRunRecord)
            .order_by(BacktestRunRecord.created_at.desc(), BacktestRunRecord.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._run(record) for record in records]

    async def mark_running(self, run_id: UUID, started_at: datetime) -> BacktestRun:
        return await self._transition(
            run_id, BacktestStatus.PENDING, BacktestStatus.RUNNING, started_at=started_at
        )

    async def mark_completed(self, run_id: UUID, completed_at: datetime) -> BacktestRun:
        return await self._transition(
            run_id, BacktestStatus.RUNNING, BacktestStatus.COMPLETED, completed_at=completed_at
        )

    async def mark_failed(
        self, run_id: UUID, failure_code: str, failure_message: str, completed_at: datetime
    ) -> BacktestRun:
        return await self._transition(
            run_id,
            BacktestStatus.RUNNING,
            BacktestStatus.FAILED,
            failure_code=failure_code,
            failure_message=failure_message,
            completed_at=completed_at,
        )

    async def _transition(
        self, run_id: UUID, expected: BacktestStatus, target: BacktestStatus, **values: Any
    ) -> BacktestRun:
        result = await self._session.execute(
            update(BacktestRunRecord)
            .where(BacktestRunRecord.id == run_id, BacktestRunRecord.status == expected)
            .values(status=target, **values)
            .returning(BacktestRunRecord)
        )
        record = result.scalar_one_or_none()
        if record is not None:
            return self._run(record)
        if (
            await self._session.scalar(
                select(BacktestRunRecord.id).where(BacktestRunRecord.id == run_id)
            )
            is None
        ):
            raise BacktestNotFoundError(f"Backtest run {run_id} was not found")
        raise InvalidBacktestTransitionError(f"Backtest run is not {expected.value}")

    @staticmethod
    def _run(record: BacktestRunRecord) -> BacktestRun:
        return BacktestRun(
            id=record.id,
            strategy_name=record.strategy_name,
            strategy_version=record.strategy_version,
            start_date=record.start_date,
            end_date=record.end_date,
            parameters=record.parameters,
            data_as_of=record.data_as_of,
            status=record.status,
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            failure_code=record.failure_code,
            failure_message=record.failure_message,
        )
