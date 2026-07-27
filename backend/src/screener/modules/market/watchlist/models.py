"""Persistence models for ranked watchlist candidates."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Date, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from screener.modules.market.screening.models import ScreeningResult
from screener.shared.database import Base


class WatchlistEntry(BaseModel):
    """An immutable, provider-neutral snapshot of one ranked candidate."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    trading_date: date
    symbol: str
    rank: int
    total_score: Decimal
    component_scores: dict[str, Decimal]
    warnings: list[str]
    snapshot: ScreeningResult


class WatchlistEntryRecord(Base):
    """SQLAlchemy representation; JSON values are encoded by Pydantic."""

    __tablename__ = "watchlist_entries"
    __table_args__ = (
        UniqueConstraint("trading_date", "symbol", name="uq_watchlist_entries_date_symbol"),
        UniqueConstraint("trading_date", "rank", name="uq_watchlist_entries_date_rank"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    trading_date: Mapped[date] = mapped_column(Date, index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    rank: Mapped[int] = mapped_column(Integer)
    # Text is intentional: unlike a fixed-scale NUMERIC column it preserves every Decimal digit.
    total_score: Mapped[str] = mapped_column(Text)
    component_scores: Mapped[str] = mapped_column(Text)
    warnings: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[str] = mapped_column(Text)


__all__ = ["WatchlistEntry"]
