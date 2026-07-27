"""Read-only endpoints for persisted watchlists."""

from collections.abc import Awaitable
from datetime import date

from fastapi import APIRouter, HTTPException

from screener.api.watchlist.dependencies import WatchlistRepositoryDependency
from screener.api.watchlist.schemas import WatchlistDetailResponse, WatchlistItemResponse

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


async def _repository_call[T](operation: Awaitable[T]) -> T:
    try:
        return await operation
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Watchlist repository error") from exc


@router.get("/latest", response_model=list[WatchlistItemResponse])
async def latest(repository: WatchlistRepositoryDependency) -> list[WatchlistItemResponse]:
    entries = await _repository_call(repository.latest())
    return [WatchlistItemResponse.from_entry(entry) for entry in entries]


@router.get("/history", response_model=list[date])
async def history(repository: WatchlistRepositoryDependency) -> list[date]:
    return await _repository_call(repository.history())


@router.get("/{trading_date}", response_model=list[WatchlistItemResponse])
async def by_date(
    trading_date: date, repository: WatchlistRepositoryDependency
) -> list[WatchlistItemResponse]:
    entries = await _repository_call(repository.list(trading_date))
    if not entries:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return [WatchlistItemResponse.from_entry(entry) for entry in entries]


@router.get("/{trading_date}/{symbol}", response_model=WatchlistDetailResponse)
async def by_symbol(
    trading_date: date, symbol: str, repository: WatchlistRepositoryDependency
) -> WatchlistDetailResponse:
    entry = await _repository_call(repository.get(trading_date, symbol))
    if entry is None:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    return WatchlistDetailResponse.from_entry(entry)
