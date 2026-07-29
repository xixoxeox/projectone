"""Authenticated canonical screener metadata."""

from fastapi import APIRouter, Request

from screener.modules.identity.presentation.dependencies import CurrentUser
from screener.modules.market.screening.swing import SETUP_ORDER, SwingScreeningConfig

router = APIRouter(prefix="/screener", tags=["screener"])


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
            "daily bars only",
            "no intraday confirmation",
            "no order-book data",
            "no market capitalization",
            "no sector or theme classification",
            "no fundamentals",
            "no benchmark-relative strength",
            "no automatic trading",
            "technical conditions do not guarantee future returns",
        ],
    }
