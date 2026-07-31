import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast

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

# PostgreSQL advisory locks share a database-wide namespace. The two-key form reserves
# the first key for this job family, preventing future schedulers that also use date
# ordinals from accidentally contending with watchlist execution acquisition.
WATCHLIST_PIPELINE_LOCK_NAMESPACE = 1001


class PipelineExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def acquire(
        self,
        trading_date: date,
        trigger: TriggerType,
        stale_after_seconds: int = 7200,
        *,
        force_reanalysis: bool = False,
    ) -> ExecutionAcquireResult:
        """Acquire a date while holding a PostgreSQL transaction advisory lock.

        The namespace and date ordinal form a stable, collision-free key for this job family.
        The partial unique index remains a final defense against duplicate active rows.
        """
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(:namespace, :trading_date)"),
                {
                    "namespace": WATCHLIST_PIPELINE_LOCK_NAMESPACE,
                    "trading_date": trading_date.toordinal(),
                },
            )
        running = await self.session.scalar(
            select(WatchlistPipelineExecution)
            .where(
                WatchlistPipelineExecution.trading_date == trading_date,
                WatchlistPipelineExecution.status == ExecutionStatus.RUNNING.value,
            )
            .order_by(WatchlistPipelineExecution.started_at.desc())
        )
        succeeded = await self.session.scalar(
            select(WatchlistPipelineExecution)
            .where(
                WatchlistPipelineExecution.trading_date == trading_date,
                WatchlistPipelineExecution.status == ExecutionStatus.SUCCEEDED.value,
            )
            .order_by(WatchlistPipelineExecution.started_at.desc())
        )
        if running is None and succeeded is not None and not force_reanalysis:
            await self.session.rollback()
            return ExecutionAcquireResult(
                status=ExecutionAcquireStatus.ALREADY_COMPLETED, execution=succeeded
            )
        if running is None and succeeded is None and force_reanalysis:
            await self.session.rollback()
            return ExecutionAcquireResult(status=ExecutionAcquireStatus.PRIOR_SUCCESS_REQUIRED)
        recovered_id = None
        now = datetime.now(UTC)
        if running is not None:
            started_at = running.started_at
            if started_at.tzinfo is None:  # SQLite test databases discard timezone metadata.
                started_at = started_at.replace(tzinfo=UTC)
            if started_at >= now - timedelta(seconds=stale_after_seconds):
                # No state changed; rollback avoids an unnecessary database commit and
                # releases the transaction-scoped advisory lock immediately.
                await self.session.rollback()
                return ExecutionAcquireResult(
                    status=ExecutionAcquireStatus.ALREADY_RUNNING, execution=running
                )
            running.status = ExecutionStatus.FAILED.value
            running.finished_at = now
            running.error_code = "stale_execution_recovered"
            running.error_detail = "Execution exceeded stale timeout"
            recovered_id = running.id
            await self.session.flush()
            if force_reanalysis and succeeded is None:
                await self.session.commit()
                return ExecutionAcquireResult(
                    status=ExecutionAcquireStatus.PRIOR_SUCCESS_REQUIRED,
                    recovered_execution_id=recovered_id,
                )
            if not force_reanalysis and succeeded is not None:
                await self.session.commit()
                return ExecutionAcquireResult(
                    status=ExecutionAcquireStatus.ALREADY_COMPLETED,
                    execution=succeeded,
                    recovered_execution_id=recovered_id,
                )
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
        screened_count: int | None = None,
        candidate_count: int | None = None,
        qualified_count: int | None = None,
        score_threshold: Decimal | None = None,
        persisted_count: int | None = None,
        skipped_reason: str | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
        commit: bool = True,
    ) -> WatchlistPipelineExecution:
        run = await self.session.get(WatchlistPipelineExecution, execution_id)
        if run is None:
            raise LookupError("pipeline execution disappeared")
        run.status, run.stage, run.finished_at = status.value, stage.value, datetime.now(UTC)
        run.screened_count = screened_count
        run.candidate_count = candidate_count
        run.qualified_count = qualified_count
        run.score_threshold = score_threshold
        run.persisted_count = persisted_count
        run.skipped_reason, run.error_code, run.error_detail = (
            skipped_reason,
            error_code,
            error_detail,
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
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

    async def latest_succeeded(self, trading_date: date) -> WatchlistPipelineExecution | None:
        return cast(
            WatchlistPipelineExecution | None,
            await self.session.scalar(
                select(WatchlistPipelineExecution)
                .where(
                    WatchlistPipelineExecution.trading_date == trading_date,
                    WatchlistPipelineExecution.status == ExecutionStatus.SUCCEEDED.value,
                )
                .order_by(WatchlistPipelineExecution.started_at.desc())
                .limit(1)
            ),
        )
