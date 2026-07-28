from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from screener.api.backtests.dependencies import BacktestServiceDependency
from screener.api.backtests.schemas import BacktestCreateRequest, BacktestResponse
from screener.modules.backtest.service import BacktestNotFoundError, BacktestRangeError

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("", response_model=BacktestResponse, status_code=status.HTTP_201_CREATED)
async def create_backtest(
    request: BacktestCreateRequest, service: BacktestServiceDependency
) -> BacktestResponse:
    try:
        run = await service.create(
            request.strategy_name,
            request.start_date,
            request.end_date,
            request.strategy_version,
            request.parameters,
            request.data_as_of,
        )
    except (ValueError, BacktestRangeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BacktestResponse.model_validate(run)


@router.get("", response_model=list[BacktestResponse])
async def list_backtests(service: BacktestServiceDependency) -> list[BacktestResponse]:
    return [BacktestResponse.model_validate(run) for run in await service.list()]


@router.get("/{run_id}", response_model=BacktestResponse)
async def get_backtest(run_id: UUID, service: BacktestServiceDependency) -> BacktestResponse:
    try:
        run = await service.get(run_id)
    except BacktestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Backtest run not found") from exc
    return BacktestResponse.model_validate(run)
