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

    @classmethod
    def from_entry(cls, entry: WatchlistEntry) -> "WatchlistItemResponse":
        return cls(
            rank=entry.rank,
            symbol=entry.symbol,
            total_score=entry.total_score,
            component_scores=entry.component_scores,
            warnings=entry.warnings,
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
