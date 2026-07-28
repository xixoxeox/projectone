from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.identity.presentation.dependencies import AdminUser
from screener.modules.market.infrastructure.repositories import SyncJobRepository
from screener.modules.market.pipeline import PipelineResult, TriggerType
from screener.modules.market.presentation.schemas import (
    SyncJobRunResponse,
    SyncJobStatusResponse,
    SyncResultResponse,
)
from screener.modules.market.sync import SyncCoordinator
from screener.modules.notifications.pipeline import NotificationPublishingPipeline
from screener.shared.database import get_db_session

router = APIRouter(prefix="/admin/sync", tags=["admin-sync"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


def coordinator(request: Request) -> SyncCoordinator:
    return cast(SyncCoordinator, request.app.state.sync_coordinator)


def watchlist_pipeline(request: Request) -> NotificationPublishingPipeline:
    return cast(NotificationPublishingPipeline, request.app.state.notification_publishing_pipeline)


@router.post("/watchlist/run")
async def run_watchlist(
    _: AdminUser,
    pipeline: Annotated[NotificationPublishingPipeline, Depends(watchlist_pipeline)],
) -> PipelineResult:
    """Generate a watchlist from the latest persisted market data."""
    return await pipeline.run(TriggerType.MANUAL)


@router.post("/stocks", response_model=SyncResultResponse)
async def stocks(
    _: AdminUser, value: Annotated[SyncCoordinator, Depends(coordinator)]
) -> SyncResultResponse:
    return SyncResultResponse.model_validate(await value.stocks.run())


@router.post("/daily-bars", response_model=SyncResultResponse)
async def daily_bars(
    _: AdminUser, value: Annotated[SyncCoordinator, Depends(coordinator)]
) -> SyncResultResponse:
    return SyncResultResponse.model_validate(await value.bars.run())


@router.post("/all", response_model=list[SyncResultResponse])
async def all_jobs(
    _: AdminUser, value: Annotated[SyncCoordinator, Depends(coordinator)]
) -> list[SyncResultResponse]:
    return [SyncResultResponse.model_validate(result) for result in await value.all()]


@router.get("/status", response_model=list[SyncJobStatusResponse])
async def status(_: AdminUser, session: Session) -> list[SyncJobStatusResponse]:
    jobs = await SyncJobRepository(session).status()
    return [
        SyncJobStatusResponse(
            job_name=x.name,
            enabled=x.enabled,
            last_success_at=x.last_success_at,
            last_failure_at=x.last_failure_at,
            last_cursor=x.last_cursor,
        )
        for x in jobs
    ]


@router.get("/history", response_model=list[SyncJobRunResponse])
async def history(
    _: AdminUser, session: Session, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[SyncJobRunResponse]:
    runs = await SyncJobRepository(session).history(limit)
    return [
        SyncJobRunResponse(
            id=x.id,
            job_name=x.job_name,
            started_at=x.started_at,
            finished_at=x.finished_at,
            duration_ms=x.duration_ms,
            status=x.status,
            inserted_rows=x.inserted_rows,
            updated_rows=x.updated_rows,
            skipped_rows=x.skipped_rows,
            error_message=x.error_message,
        )
        for x in runs
    ]
