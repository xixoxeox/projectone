"""Authenticated canonical screener definition contract."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from screener.modules.identity.presentation.dependencies import CurrentUser
from screener.modules.market.screening.swing import CONFIG, SwingScreeningConfig

router = APIRouter(prefix="/screener", tags=["screener"])


def get_screener_config() -> SwingScreeningConfig:
    return CONFIG


class SetupDefinition(BaseModel):
    key: str
    label: str
    description: str


class ScreenerDefinitions(BaseModel):
    screener_name: str
    screener_version: str
    setups: list[SetupDefinition]
    defaults: dict[str, Any]
    limitations: list[str]


@router.get("/definitions", response_model=ScreenerDefinitions)
async def definitions(
    _user: CurrentUser,
    config: Annotated[SwingScreeningConfig, Depends(get_screener_config)],
) -> ScreenerDefinitions:
    return ScreenerDefinitions(
        screener_name=config.screener_name,
        screener_version=config.screener_version,
        setups=[
            SetupDefinition(
                key="box_breakout",
                label="박스권 돌파",
                description="좁은 가격 범위를 거래량과 함께 상향 돌파한 후보",
            ),
            SetupDefinition(
                key="trend_pullback",
                label="추세 눌림목",
                description="상승 추세에서 거래량이 감소한 눌림 후 반등 후보",
            ),
            SetupDefinition(
                key="volatility_contraction_breakout",
                label="변동성 축소 돌파",
                description="가격·거래량 변동성 축소 후 돌파한 후보",
            ),
        ],
        defaults=config.model_dump(mode="json"),
        limitations=[
            "daily_bars_only",
            "no_market_cap_filter",
            "no_sector_or_theme",
            "no_fundamentals",
            "not_an_automatic_trade_signal",
        ],
    )
