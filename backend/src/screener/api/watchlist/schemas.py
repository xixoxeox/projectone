"""Public response schemas for persisted watchlists."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

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
    matched_setups: list[str] = Field(default_factory=list)
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
        snapshot = entry.snapshot
        setup_metrics = snapshot.setup_metrics.get(snapshot.primary_setup or "", {})
        return cls(
            rank=entry.rank,
            symbol=entry.symbol,
            total_score=entry.total_score,
            component_scores=entry.component_scores,
            warnings=entry.warnings,
            primary_setup=snapshot.primary_setup,
            matched_setups=snapshot.matched_setups,
            screener_name=snapshot.screener_name,
            screener_version=snapshot.screener_version,
            **{
                "latest_close": snapshot.metrics.get("latest_close"),
                "average_trading_value_20": snapshot.metrics.get("average_trading_value_20"),
                "atr_pct": snapshot.metrics.get("atr_pct"),
                "volume_ratio": setup_metrics.get("volume_ratio")
                if snapshot.primary_setup == "box_breakout"
                else None,
                "prior_short_volume_ratio": setup_metrics.get("prior_short_volume_ratio")
                if snapshot.primary_setup
                in {
                    "trend_pullback",
                    "volatility_contraction_breakout",
                }
                else None,
                "breakout_volume_ratio": setup_metrics.get("breakout_volume_ratio")
                if snapshot.primary_setup == "volatility_contraction_breakout"
                else None,
            },
        )


class WatchlistDetailResponse(WatchlistItemResponse):
    """Inspection view of an entry, including its screening snapshot."""

    trading_date: date
    snapshot: ScreeningResult
    metrics: dict[str, Decimal]
    reasons: list[str]
    setup_scores: dict[str, Decimal]
    configuration_snapshot: dict[str, str | int]
    setup_metrics: dict[str, dict[str, Decimal]]
    rule_evaluations: dict[str, bool]

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
            setup_scores=entry.snapshot.setup_scores,
            configuration_snapshot=entry.snapshot.configuration_snapshot,
            setup_metrics=entry.snapshot.setup_metrics,
            rule_evaluations=entry.snapshot.rule_evaluations,
        )
