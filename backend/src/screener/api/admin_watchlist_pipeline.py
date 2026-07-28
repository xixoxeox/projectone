"""Dedicated administration API for the canonical watchlist pipeline."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.identity.presentation.dependencies import AdminUser
from screener.modules.market.pipeline import PipelineResult, TriggerType
from screener.modules.market.pipeline.repository import PipelineExecutionRepository
from screener.modules.notifications import NotificationPublishingPipeline
from screener.shared.database import get_db_session

router = APIRouter(prefix="/admin/watchlist-pipeline", tags=["admin-watchlist-pipeline"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


def watchlist_pipeline(request: Request) -> NotificationPublishingPipeline:
    return cast(NotificationPublishingPipeline, request.app.state.notification_publishing_pipeline)


@router.post("/run", response_model=None)
async def run_watchlist(
    _: AdminUser,
    pipeline: Annotated[NotificationPublishingPipeline, Depends(watchlist_pipeline)],
) -> PipelineResult:
    return await pipeline.run(TriggerType.MANUAL)


@router.get("/history", response_model=None)
async def execution_history(
    _: AdminUser, session: Session, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[dict[str, object]]:
    executions = await PipelineExecutionRepository(session).history(limit)
    return [
        {
            "execution_id": item.id,
            "trading_date": item.trading_date,
            "trigger_type": item.trigger_type,
            "status": item.status,
            "started_at": item.started_at,
            "finished_at": item.finished_at,
            "candidate_count": item.candidate_count,
            "persisted_count": item.persisted_count,
            "stage": item.stage,
            "error_code": item.error_code,
            "recovered_execution_id": item.recovered_execution_id,
        }
        for item in executions
    ]
