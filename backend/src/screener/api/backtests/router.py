"""REST endpoints for creating and inspecting backtest run metadata."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from screener.api.backtests.dependencies import BacktestServiceDependency
from screener.api.backtests.schemas import BacktestResponse, CreateBacktestRequest
from screener.modules.backtest import (
    BacktestExecutionError,
    BacktestNotFoundError,
    InvalidBacktestRangeError,
    InvalidBacktestTransitionError,
)

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("", response_model=BacktestResponse, status_code=status.HTTP_201_CREATED)
async def create(
    request: CreateBacktestRequest, service: BacktestServiceDependency
) -> BacktestResponse:
    try:
        run = await service.create(
            request.strategy_name,
            request.strategy_version,
            request.start_date,
            request.end_date,
            request.parameters,
            request.data_as_of,
        )
    except InvalidBacktestRangeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InvalidBacktestTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BacktestExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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
    try:
        run = await service.get(run_id)
    except BacktestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Backtest run not found") from exc
    return BacktestResponse.from_run(run)
