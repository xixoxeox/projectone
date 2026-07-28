from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from screener.modules.backtest.domain import BacktestExitReason, BacktestStatus
from screener.shared.database import Base


class BacktestRunRecord(Base):
    __tablename__ = "backtest_runs"
    __table_args__ = (CheckConstraint("start_date <= end_date", name="date_range"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    strategy_name: Mapped[str] = mapped_column(String(100), index=True)
    strategy_version: Mapped[str | None] = mapped_column(String(100))
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=dict
    )
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[BacktestStatus] = mapped_column(
        Enum(
            BacktestStatus,
            name="backtest_status",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        index=True,
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class BacktestTradeRecord(Base):
    __tablename__ = "backtest_trades"
    __table_args__ = (
        UniqueConstraint("run_id", "symbol", "signal_date", name="uq_backtest_trade_signal"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"), index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    signal_date: Mapped[date] = mapped_column(Date)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    quantity: Mapped[int] = mapped_column(Integer)
    exit_date: Mapped[date] = mapped_column(Date, index=True)
    exit_price: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    exit_reason: Mapped[BacktestExitReason] = mapped_column(
        Enum(
            BacktestExitReason,
            name="backtest_exit_reason",
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    gross_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    commission: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    tax: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    slippage_cost: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    net_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    holding_days: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
