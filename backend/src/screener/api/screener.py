"""Authenticated canonical screener metadata."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from screener.api.watchlist.schemas import WatchlistItemResponse
from screener.modules.identity.presentation.dependencies import CurrentUser
from screener.modules.market.pipeline import PipelineExecutionRepository
from screener.modules.market.screening.swing import SETUP_ORDER, SwingScreeningConfig
from screener.modules.market.watchlist import WatchlistRepository
from screener.shared.database import get_db_session

router = APIRouter(prefix="/screener", tags=["screener"])


class ScreenerResultsResponse(BaseModel):
    execution_id: uuid.UUID | None = None
    trading_date: date
    screened_count: int | None = Field(default=None, ge=0)
    setup_passed_count: int | None = Field(default=None, ge=0)
    score_qualified_count: int | None = Field(default=None, ge=0)
    score_threshold: Decimal | None = Field(default=None, ge=0, le=100)
    result_count: int | None = Field(default=None, ge=0)
    items: list[WatchlistItemResponse]


@router.get("/definitions")
async def definitions(_: CurrentUser, request: Request) -> dict[str, object]:
    config: SwingScreeningConfig = request.app.state.swing_screening_config
    labels = {
        "box_breakout": "박스권 돌파",
        "trend_pullback": "추세 눌림목",
        "volatility_contraction_breakout": "변동성 축소 돌파",
    }
    return {
        "screener_name": config.screener_name,
        "version": config.screener_version,
        "setup_keys": list(SETUP_ORDER),
        "setup_labels": labels,
        "descriptions": {key: labels[key] for key in SETUP_ORDER},
        "defaults": config.snapshot(),
        "limitations": [
            "scheduled screening uses daily bars",
            "no order-book data",
            "no market capitalization",
            "no sector or theme classification",
            "no fundamentals",
            "no benchmark-relative strength",
            "no automatic trading",
            "technical conditions do not guarantee future returns",
        ],
    }


@router.get("/results/{trading_date}", response_model=ScreenerResultsResponse)
async def results(
    _: CurrentUser,
    trading_date: date,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ScreenerResultsResponse:
    execution = await PipelineExecutionRepository(session).latest_succeeded(trading_date)
    watchlist = WatchlistRepository(session)
    if execution is None and not await watchlist.exists(trading_date):
        raise HTTPException(status_code=404, detail="Screener result not found")
    entries = await watchlist.list(trading_date)
    if execution is None:
        return ScreenerResultsResponse(
            trading_date=trading_date,
            result_count=len(entries),
            items=[WatchlistItemResponse.from_entry(entry) for entry in entries],
        )
    return ScreenerResultsResponse(
        execution_id=execution.id,
        trading_date=execution.trading_date,
        screened_count=execution.screened_count,
        setup_passed_count=execution.candidate_count,
        score_qualified_count=execution.qualified_count,
        score_threshold=execution.score_threshold,
        result_count=execution.persisted_count,
        items=[WatchlistItemResponse.from_entry(entry) for entry in entries],
    )
