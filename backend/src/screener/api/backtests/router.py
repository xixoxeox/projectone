"""REST endpoints for creating and inspecting backtest run metadata."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from screener.api.backtests.dependencies import BacktestServiceDependency
from screener.api.backtests.schemas import BacktestResponse, CreateBacktestRequest

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("", response_model=BacktestResponse, status_code=status.HTTP_201_CREATED)
async def create(
    request: CreateBacktestRequest, service: BacktestServiceDependency
) -> BacktestResponse:
    run = await service.create(
        request.strategy_name, request.start_date, request.end_date, request.parameters
    )
    return BacktestResponse.from_run(run)


@router.get("", response_model=list[BacktestResponse])
async def list_runs(
    service: BacktestServiceDependency,
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[BacktestResponse]:
    return [BacktestResponse.from_run(run) for run in await service.list(limit, offset)]


@router.get("/{run_id}", response_model=BacktestResponse)
async def get(run_id: UUID, service: BacktestServiceDependency) -> BacktestResponse:
    run = await service.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return BacktestResponse.from_run(run)
