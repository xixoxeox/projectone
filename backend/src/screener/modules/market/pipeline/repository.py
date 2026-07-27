import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.market.infrastructure.models import WatchlistPipelineExecution
from screener.modules.market.pipeline.models import (
    ExecutionAcquireResult,
    ExecutionAcquireStatus,
    ExecutionStatus,
    PipelineStage,
    TriggerType,
)


class PipelineExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def acquire(
        self, trading_date: date, trigger: TriggerType, stale_after_seconds: int = 7200
    ) -> ExecutionAcquireResult:
        """Acquire a date while holding a PostgreSQL transaction advisory lock.

        The date ordinal is a stable, collision-free key within the supported date domain.
        The partial unique index remains a final defense against duplicate active rows.
        """
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": trading_date.toordinal()},
            )
        active = await self.session.scalar(
            select(WatchlistPipelineExecution)
            .where(
                WatchlistPipelineExecution.trading_date == trading_date,
                WatchlistPipelineExecution.status.in_(
                    [ExecutionStatus.RUNNING.value, ExecutionStatus.SUCCEEDED.value]
                ),
            )
            .order_by(WatchlistPipelineExecution.started_at.desc())
        )
        if active is not None and active.status == ExecutionStatus.SUCCEEDED.value:
            await self.session.commit()
            return ExecutionAcquireResult(
                status=ExecutionAcquireStatus.ALREADY_COMPLETED, execution=active
            )
        recovered_id = None
        now = datetime.now(UTC)
        if active is not None:
            started_at = active.started_at
            if started_at.tzinfo is None:  # SQLite test databases discard timezone metadata.
                started_at = started_at.replace(tzinfo=UTC)
            if started_at >= now - timedelta(seconds=stale_after_seconds):
                await self.session.commit()
                return ExecutionAcquireResult(
                    status=ExecutionAcquireStatus.ALREADY_RUNNING, execution=active
                )
            active.status = ExecutionStatus.FAILED.value
            active.finished_at = now
            active.error_code = "stale_execution_recovered"
            active.error_detail = "Execution exceeded stale timeout"
            recovered_id = active.id
            await self.session.flush()
        run = WatchlistPipelineExecution(
            trading_date=trading_date,
            trigger_type=trigger.value,
            status=ExecutionStatus.RUNNING.value,
            stage=PipelineStage.DUPLICATE_CHECK.value,
            started_at=now,
        )
        self.session.add(run)
        await self.session.commit()
        return ExecutionAcquireResult(
            status=ExecutionAcquireStatus.ACQUIRED,
            execution=run,
            recovered_execution_id=recovered_id,
        )

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
