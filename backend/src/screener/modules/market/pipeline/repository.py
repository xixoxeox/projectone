"""Canonical persistence repository for watchlist pipeline executions."""

from datetime import UTC, date, datetime, timedelta
from typing import cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.market.infrastructure.models import WatchlistPipelineExecution


class PipelineExecutionRepository:
    """Persist ownership and outcomes for the canonical watchlist pipeline."""

    LOCK_KEY = 0x57415443484C4953

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def acquire_lock(self) -> bool:
        if self.session.bind is None or self.session.bind.dialect.name != "postgresql":
            return True
        return bool(
            await self.session.scalar(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": self.LOCK_KEY}
            )
        )

    async def successful(self, trading_date: date) -> WatchlistPipelineExecution | None:
        return cast(
            WatchlistPipelineExecution | None,
            await self.session.scalar(
                select(WatchlistPipelineExecution)
                .where(
                    WatchlistPipelineExecution.trading_date == trading_date,
                    WatchlistPipelineExecution.status == "succeeded",
                )
                .order_by(WatchlistPipelineExecution.finished_at.desc())
                .limit(1)
            ),
        )

    async def recover_stale(
        self, trading_date: date, stale_after: timedelta
    ) -> WatchlistPipelineExecution | None:
        execution = await self.session.scalar(
            select(WatchlistPipelineExecution)
            .where(
                WatchlistPipelineExecution.trading_date == trading_date,
                WatchlistPipelineExecution.status == "running",
                WatchlistPipelineExecution.heartbeat_at < datetime.now(UTC) - stale_after,
            )
            .order_by(WatchlistPipelineExecution.started_at)
            .with_for_update()
            .limit(1)
        )
        if execution is not None:
            execution.status = "recovered"
            execution.finished_at = datetime.now(UTC)
            execution.error_code = "stale_execution_recovered"
        return execution

    async def history(self, limit: int = 50) -> list[WatchlistPipelineExecution]:
        return list(
            (
                await self.session.scalars(
                    select(WatchlistPipelineExecution)
                    .order_by(WatchlistPipelineExecution.started_at.desc())
                    .limit(limit)
                )
            ).all()
        )
