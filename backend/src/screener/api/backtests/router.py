from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from screener.api.backtests.dependencies import BacktestServiceDependency
from screener.api.backtests.schemas import (
    BacktestAnalysisResponse,
    BacktestCreateRequest,
    BacktestResponse,
    BacktestTradeResponse,
    PortfolioResponse,
    PortfolioSnapshotResponse,
)
from screener.modules.backtest.domain import BacktestExitReason
from screener.modules.backtest.service import (
    BacktestAnalysisUnavailableError,
    BacktestNotFoundError,
    BacktestRangeError,
    PortfolioUnavailableError,
)

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.get("/{run_id}/portfolio", response_model=PortfolioResponse)
async def get_backtest_portfolio(
    run_id: UUID, service: BacktestServiceDependency
) -> PortfolioResponse:
    try:
        run, snapshots = await service.portfolio(run_id)
    except BacktestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Backtest run not found") from exc
    except PortfolioUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result = run.result or {}
    return PortfolioResponse(
        run_id=run.id,
        initial_capital=result["initial_capital"],
        final_equity=result["final_equity"],
        final_cash=result["final_cash"],
        net_profit=result["net_profit"],
        total_return=result["total_return"],
        max_drawdown=result["max_drawdown"],
        max_drawdown_pct=result["max_drawdown_pct"],
        maximum_open_positions_used=result["maximum_open_positions_used"],
        average_capital_utilization=result["average_capital_utilization"],
        snapshots=[PortfolioSnapshotResponse.model_validate(item) for item in snapshots],
    )


@router.get("/{run_id}/analysis", response_model=BacktestAnalysisResponse)
async def get_backtest_analysis(
    run_id: UUID, service: BacktestServiceDependency
) -> BacktestAnalysisResponse:
    try:
        analysis = await service.analyze(run_id)
    except BacktestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Backtest run not found") from exc
    except BacktestAnalysisUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return BacktestAnalysisResponse.model_validate(analysis)


@router.post("", response_model=BacktestResponse, status_code=status.HTTP_201_CREATED)
async def create_backtest(
    request: BacktestCreateRequest, service: BacktestServiceDependency
) -> BacktestResponse:
    try:
        parameters = dict(request.parameters)
        if "execution_mode" in request.model_fields_set:
            parameters["execution_mode"] = request.execution_mode
        run = await service.create(
            request.strategy_name,
            request.start_date,
            request.end_date,
            request.strategy_version,
            parameters,
            request.data_as_of,
        )
    except (ValueError, BacktestRangeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BacktestResponse.model_validate(run)


@router.get("/{run_id}/trades", response_model=list[BacktestTradeResponse])
async def list_backtest_trades(
    run_id: UUID,
    service: BacktestServiceDependency,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    symbol: str | None = None,
    exit_reason: BacktestExitReason | None = None,
) -> list[BacktestTradeResponse]:
    try:
        trades = await service.list_trades(run_id, limit, offset, symbol, exit_reason)
    except BacktestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Backtest run not found") from exc
    return [BacktestTradeResponse.model_validate(trade) for trade in trades]


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
