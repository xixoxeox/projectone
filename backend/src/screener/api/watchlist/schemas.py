"""Public response schemas for persisted watchlists."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from screener.modules.market.screening import ScreeningResult
from screener.modules.market.watchlist import WatchlistEntry


class WatchlistItemResponse(BaseModel):
    """Summary of a ranked entry, excluding persistence and snapshot details."""

    rank: int
    symbol: str
    total_score: Decimal
    component_scores: dict[str, Decimal]
    warnings: list[str]
    primary_setup: str | None = None
    matched_setups: list[str] = []
    screener_name: str | None = None
    screener_version: str | None = None
    latest_close: Decimal | None = None
    average_trading_value_20: Decimal | None = None
    volume_ratio: Decimal | None = None
    prior_short_volume_ratio: Decimal | None = None
    breakout_volume_ratio: Decimal | None = None
    atr_pct: Decimal | None = None

    @classmethod
    def from_entry(cls, entry: WatchlistEntry) -> "WatchlistItemResponse":
        return cls(
            rank=entry.rank,
            symbol=entry.symbol,
            total_score=entry.total_score,
            component_scores=entry.component_scores,
            warnings=entry.warnings,
            primary_setup=entry.snapshot.primary_setup,
            matched_setups=entry.snapshot.matched_setups,
            screener_name=entry.snapshot.screener_name,
            screener_version=entry.snapshot.screener_version,
            **{
                key: entry.snapshot.metrics.get(key)
                for key in (
                    "latest_close",
                    "average_trading_value_20",
                    "volume_ratio",
                    "prior_short_volume_ratio",
                    "breakout_volume_ratio",
                    "atr_pct",
                )
            },
        )


class WatchlistDetailResponse(WatchlistItemResponse):
    """Inspection view of an entry, including its screening snapshot."""

    trading_date: date
    snapshot: ScreeningResult
    metrics: dict[str, Decimal]
    reasons: list[str]

    @classmethod
    def from_entry(cls, entry: WatchlistEntry) -> "WatchlistDetailResponse":
        return cls(
            rank=entry.rank,
            symbol=entry.symbol,
            total_score=entry.total_score,
            component_scores=entry.component_scores,
            warnings=entry.warnings,
            trading_date=entry.trading_date,
            snapshot=entry.snapshot,
            metrics=entry.snapshot.metrics,
            reasons=entry.snapshot.reasons,
        )
