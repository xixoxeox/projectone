from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from screener.modules.identity.infrastructure.models import User
from screener.modules.identity.presentation.dependencies import get_current_user
from screener.modules.market.infrastructure.repositories import SyncJobRepository
from screener.modules.market.sync import SyncCoordinator
from screener.shared.database import get_db_session

router = APIRouter(prefix="/admin/sync", tags=["admin-sync"])
Admin = Annotated[User, Depends(get_current_user)]
Session = Annotated[AsyncSession, Depends(get_db_session)]


def coordinator(request: Request) -> SyncCoordinator:
    return request.app.state.sync_coordinator  # type: ignore[no-any-return]


@router.post("/stocks")
async def stocks(_: Admin, value: Annotated[SyncCoordinator, Depends(coordinator)]) -> Any:
    return await value.stocks.run()


@router.post("/daily-bars")
async def daily_bars(_: Admin, value: Annotated[SyncCoordinator, Depends(coordinator)]) -> Any:
    return await value.bars.run()


@router.post("/all")
async def all_jobs(_: Admin, value: Annotated[SyncCoordinator, Depends(coordinator)]) -> Any:
    return await value.all()


@router.get("/status")
async def status(_: Admin, session: Session) -> list[dict[str, Any]]:
    jobs = await SyncJobRepository(session).status()
    return [
        {
            "job_name": x.name,
            "enabled": x.enabled,
            "last_success_at": x.last_success_at,
            "last_failure_at": x.last_failure_at,
            "last_cursor": x.last_cursor,
        }
        for x in jobs
    ]


@router.get("/history")
async def history(
    _: Admin, session: Session, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[dict[str, Any]]:
    runs = await SyncJobRepository(session).history(limit)
    return [
        {
            "id": x.id,
            "job_name": x.job_name,
            "started_at": x.started_at,
            "finished_at": x.finished_at,
            "duration_ms": x.duration_ms,
            "status": x.status,
            "inserted_rows": x.inserted_rows,
            "updated_rows": x.updated_rows,
            "skipped_rows": x.skipped_rows,
            "error_message": x.error_message,
        }
        for x in runs
    ]
