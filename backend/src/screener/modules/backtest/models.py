"""Domain and database models for backtest run lifecycle metadata."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, Date, DateTime, Enum, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from screener.shared.database import Base


class BacktestStatus(StrEnum):
    """Persistence states supported before an execution engine exists."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BacktestRun(BaseModel):
    """Provider-neutral metadata describing one requested backtest run."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    strategy_name: str
    start_date: date
    end_date: date
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: BacktestStatus = BacktestStatus.PENDING
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


class BacktestRunRecord(Base):
    """SQLAlchemy representation of lifecycle metadata only."""

    __tablename__ = "backtest_runs"
    __table_args__ = (
        CheckConstraint("start_date <= end_date", name="ck_backtest_runs_date_range"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    strategy_name: Mapped[str] = mapped_column(String(100), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    parameters: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[BacktestStatus] = mapped_column(
        Enum(
            BacktestStatus,
            name="backtest_status",
            values_callable=lambda values: [v.value for v in values],
        ),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
