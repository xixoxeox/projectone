import uuid
from datetime import date
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.identity.presentation.dependencies import AdminUser
from screener.modules.market.infrastructure.models import WatchlistPipelineExecution
from screener.modules.market.pipeline import (
    ExecutionAcquireStatus,
    PipelineExecutionRepository,
    PipelineResult,
    TriggerType,
)
from screener.modules.notifications.pipeline import PipelineRunner
from screener.shared.database import get_db_session

router = APIRouter(prefix="/admin/watchlist", tags=["admin-watchlist-pipeline"])


class RunRequest(BaseModel):
    trading_date: date | None = None
    force_reanalysis: bool = False


class ExecutionResponse(PipelineResult):
    pass


def get_pipeline(request: Request) -> PipelineRunner:
    return cast(PipelineRunner, request.app.state.daily_watchlist_pipeline)


def response(record: WatchlistPipelineExecution) -> ExecutionResponse:
    return ExecutionResponse(
        execution_id=record.id,
        trading_date=record.trading_date,
        status=record.status,
        started_at=record.started_at,
        finished_at=record.finished_at,
        stage=record.stage,
        candidate_count=record.candidate_count,
        persisted_count=record.persisted_count,
        skipped_reason=record.skipped_reason,
        error_code=record.error_code,
        trigger_type=record.trigger_type,
    )


@router.post("/run", response_model=ExecutionResponse)
async def run(
    _: AdminUser,
    pipeline: Annotated[PipelineRunner, Depends(get_pipeline)],
    body: RunRequest | None = None,
) -> PipelineResult:
    force = body.force_reanalysis if body else False
    if force and body is not None and body.trading_date is None:
        raise HTTPException(422, "trading_date is required for force_reanalysis")
    result = await pipeline.run(
        None if body is None else body.trading_date,
        TriggerType.MANUAL_REANALYSIS if force else TriggerType.MANUAL,
        force_reanalysis=force,
    )
    if result.skipped_reason == "already_running":
        raise HTTPException(409, "A run is already active")
    if result.skipped_reason == ExecutionAcquireStatus.PRIOR_SUCCESS_REQUIRED.value:
        raise HTTPException(409, "A prior successful execution is required for reanalysis")
    if result.status == "failed":
        raise HTTPException(500, detail={"error_code": result.error_code})
    return result


@router.get("/executions/latest", response_model=ExecutionResponse)
async def latest(
    _: AdminUser, session: Annotated[AsyncSession, Depends(get_db_session)]
) -> ExecutionResponse:
    records = await PipelineExecutionRepository(session).list(1)
    if not records:
        raise HTTPException(404, "No execution found")
    return response(records[0])


@router.get("/executions", response_model=list[ExecutionResponse])
async def executions(
    _: AdminUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ExecutionResponse]:
    return [response(record) for record in await PipelineExecutionRepository(session).list(limit)]


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def execution(
    _: AdminUser, execution_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db_session)]
) -> ExecutionResponse:
    record = await PipelineExecutionRepository(session).get(execution_id)
    if record is None:
        raise HTTPException(404, "Execution not found")
    return response(record)
