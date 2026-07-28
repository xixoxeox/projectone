"""Persistence operations for backtest run lifecycle metadata."""

import json
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.backtest.models import BacktestRun, BacktestRunRecord, BacktestStatus


class BacktestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        strategy_name: str,
        start_date: date,
        end_date: date,
        parameters: Mapping[str, Any],
        created_at: datetime,
    ) -> BacktestRun:
        record = BacktestRunRecord(
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            parameters=json.dumps(parameters, separators=(",", ":"), sort_keys=True),
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

    async def update_status(
        self,
        run_id: UUID,
        status: BacktestStatus,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> BacktestRun | None:
        record = await self._session.get(BacktestRunRecord, run_id)
        if record is None:
            return None
        record.status = status
        record.started_at = started_at
        record.completed_at = completed_at
        record.error_message = error_message
        await self._session.flush()
        return self._run(record)

    @staticmethod
    def _run(record: BacktestRunRecord) -> BacktestRun:
        return BacktestRun(
            id=record.id,
            strategy_name=record.strategy_name,
            start_date=record.start_date,
            end_date=record.end_date,
            parameters=json.loads(record.parameters),
            status=record.status,
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            error_message=record.error_message,
        )
