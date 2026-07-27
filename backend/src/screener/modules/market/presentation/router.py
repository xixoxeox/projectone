from datetime import date
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from screener.config import get_settings
from screener.modules.identity.presentation.dependencies import CurrentUser
from screener.modules.market.application import BarsResult, MarketDataService
from screener.modules.market.domain import ProviderError, ProviderStatus
from screener.modules.market.infrastructure.toss import TossMarketDataProvider

router = APIRouter(tags=["market-data"])


@lru_cache
def get_market_data_service() -> MarketDataService:
    settings = get_settings()
    client = httpx.AsyncClient(
        base_url=settings.toss_api_base_url,
        timeout=httpx.Timeout(settings.toss_request_timeout_seconds),
    )
    # Official Toss paths, token payload, and response fields are not present in the
    # approved project documents. Deliberately remain unconfigured rather than guessing.
    provider = TossMarketDataProvider(client, None, None, settings.toss_max_retries)
    return MarketDataService(provider)


Service = Annotated[MarketDataService, Depends(get_market_data_service)]


@router.get("/operations/providers/market-data", response_model=ProviderStatus)
async def provider_status(_user: CurrentUser, service: Service) -> ProviderStatus:
    return await service.status()


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
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderError as exc:
        status_code = 503 if exc.retryable or "unverified" in str(exc) else 502
        raise HTTPException(
            status_code=status_code,
            detail={"code": type(exc).__name__, "message": str(exc), "provider": exc.provider},
        ) from exc
