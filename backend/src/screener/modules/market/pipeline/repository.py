import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.market.infrastructure.models import WatchlistPipelineExecution
from screener.modules.market.pipeline.models import ExecutionStatus, PipelineStage, TriggerType


class PipelineExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def acquire(
        self, trading_date: date, trigger: TriggerType
    ) -> WatchlistPipelineExecution | None:
        run = WatchlistPipelineExecution(
            trading_date=trading_date,
            trigger_type=trigger.value,
            status=ExecutionStatus.RUNNING.value,
            stage=PipelineStage.DUPLICATE_CHECK.value,
            started_at=datetime.now(UTC),
        )
        self.session.add(run)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return None
        return run

    async def set_stage(self, execution_id: uuid.UUID, stage: PipelineStage) -> None:
        run = await self.session.get(WatchlistPipelineExecution, execution_id)
        if run is None:
            raise LookupError("pipeline execution disappeared")
        run.stage = stage.value
        await self.session.commit()

    async def finish(
        self,
        execution_id: uuid.UUID,
        *,
        status: ExecutionStatus,
        stage: PipelineStage,
        candidate_count: int | None = None,
        persisted_count: int | None = None,
        skipped_reason: str | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> WatchlistPipelineExecution:
        run = await self.session.get(WatchlistPipelineExecution, execution_id)
        if run is None:
            raise LookupError("pipeline execution disappeared")
        run.status, run.stage, run.finished_at = status.value, stage.value, datetime.now(UTC)
        run.candidate_count, run.persisted_count = candidate_count, persisted_count
        run.skipped_reason, run.error_code, run.error_detail = (
            skipped_reason,
            error_code,
            error_detail,
        )
        await self.session.commit()
        return run

    async def list(self, limit: int = 50) -> list[WatchlistPipelineExecution]:
        return list(
            (
                await self.session.scalars(
                    select(WatchlistPipelineExecution)
                    .order_by(WatchlistPipelineExecution.started_at.desc())
                    .limit(limit)
                )
            ).all()
        )

    async def get(self, execution_id: uuid.UUID) -> WatchlistPipelineExecution | None:
        return await self.session.get(WatchlistPipelineExecution, execution_id)
