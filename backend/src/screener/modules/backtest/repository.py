from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.backtest.domain import BacktestRun, BacktestStatus
from screener.modules.backtest.models import BacktestRunRecord


class BacktestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, run: BacktestRun) -> BacktestRun:
        record = await self.session.get(BacktestRunRecord, run.id)
        if record is None:
            record = BacktestRunRecord(id=run.id)
            self.session.add(record)
        record.strategy_name = run.strategy_name
        record.strategy_version = run.strategy_version
        record.parameters = run.parameters
        record.start_date = run.start_date
        record.end_date = run.end_date
        record.data_as_of = run.data_as_of
        record.status = run.status
        record.result = run.result
        record.failure_code = run.failure_code
        record.failure_message = run.failure_message
        record.started_at = run.started_at
        record.completed_at = run.completed_at
        record.created_at = run.created_at
        await self.session.flush()
        return run

    async def get(self, run_id: UUID) -> BacktestRun | None:
        record = await self.session.get(BacktestRunRecord, run_id)
        return self._domain(record) if record else None

    async def list(self) -> list[BacktestRun]:
        result = await self.session.scalars(
            select(BacktestRunRecord).order_by(BacktestRunRecord.created_at.desc())
        )
        return [self._domain(record) for record in result]

    @staticmethod
    def _domain(record: BacktestRunRecord) -> BacktestRun:
        return BacktestRun(
            id=record.id,
            strategy_name=record.strategy_name,
            strategy_version=record.strategy_version,
            parameters=record.parameters,
            start_date=record.start_date,
            end_date=record.end_date,
            data_as_of=record.data_as_of,
            status=BacktestStatus(record.status),
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            result=record.result,
            failure_code=record.failure_code,
            failure_message=record.failure_message,
        )
