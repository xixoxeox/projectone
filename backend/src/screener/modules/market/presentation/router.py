from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from screener.modules.identity.presentation.dependencies import CurrentUser
from screener.modules.market.application import BarsResult, MarketDataService, PricesResult
from screener.modules.market.domain import (
    InstrumentSnapshot,
    ProviderAuthenticationError,
    ProviderError,
    ProviderForbiddenError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderStatus,
    ProviderValidationError,
    StockWarning,
)
from screener.modules.market.technical_analysis import RealtimeTechnicalAnalysis

router = APIRouter(tags=["market-data"])


def get_market_data_service(request: Request) -> MarketDataService:
    return request.app.state.market_data_service  # type: ignore[no-any-return]


Service = Annotated[MarketDataService, Depends(get_market_data_service)]


def _raise(exc: Exception) -> None:
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    assert isinstance(exc, ProviderError)
    status = 502
    if isinstance(exc, (ProviderValidationError,)):
        status = 422
    elif isinstance(exc, ProviderAuthenticationError):
        status = 502
    elif isinstance(exc, ProviderForbiddenError):
        status = 503
    elif isinstance(exc, ProviderNotFoundError):
        status = 404
    elif isinstance(exc, ProviderRateLimitError) or exc.retryable:
        status = 503
    detail: dict[str, Any] = {
        "code": type(exc).__name__,
        "message": str(exc),
        "provider": exc.provider,
    }
    if exc.request_id:
        detail["request_id"] = exc.request_id
    if exc.provider_code:
        detail["provider_code"] = exc.provider_code
    raise HTTPException(status_code=status, detail=detail) from exc


@router.get("/operations/providers/market-data", response_model=ProviderStatus)
async def provider_status(_user: CurrentUser, service: Service) -> ProviderStatus:
    return await service.status()


@router.get("/instruments/prices", response_model=PricesResult)
async def prices(
    symbols: Annotated[str, Query(min_length=1)], _user: CurrentUser, service: Service
) -> PricesResult:
    try:
        return await service.prices(symbols.split(","))
    except (ValueError, ProviderError) as exc:
        _raise(exc)
    raise AssertionError("unreachable")


@router.get("/instruments/{symbol}", response_model=InstrumentSnapshot)
async def instrument(symbol: str, _user: CurrentUser, service: Service) -> InstrumentSnapshot:
    try:
        return await service.instrument(symbol)
    except (ValueError, ProviderError) as exc:
        _raise(exc)
    raise AssertionError("unreachable")


@router.get("/instruments/{symbol}/warnings", response_model=list[StockWarning])
async def warnings(symbol: str, _user: CurrentUser, service: Service) -> list[StockWarning]:
    try:
        return await service.warnings(symbol)
    except (ValueError, ProviderError) as exc:
        _raise(exc)
    raise AssertionError("unreachable")


@router.get("/instruments/{symbol}/analysis", response_model=RealtimeTechnicalAnalysis)
async def realtime_analysis(
    symbol: str,
    _user: CurrentUser,
    service: Service,
) -> RealtimeTechnicalAnalysis:
    try:
        return await service.realtime_analysis(symbol)
    except (ValueError, ProviderError) as exc:
        _raise(exc)
    raise AssertionError("unreachable")


@router.get("/instruments/{symbol}/bars", response_model=BarsResult)
async def daily_bars(
    symbol: str,
    start_date: Annotated[date, Query()],
    end_date: Annotated[date, Query()],
    _user: CurrentUser,
    service: Service,
) -> BarsResult:
    try:
        return await service.daily_bars(symbol, start_date, end_date)
    except (ValueError, ProviderError) as exc:
        _raise(exc)
    raise AssertionError("unreachable")
