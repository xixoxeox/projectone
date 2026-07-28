"""Persist deterministic backtest trades."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_backtest_trades"
down_revision = "0005_backtest_runs"
branch_labels = None
depends_on = None
exit_reason = postgresql.ENUM(
    "stop_loss",
    "take_profit",
    "max_holding_days",
    "end_of_period",
    "no_entry_bar",
    "insufficient_position_size",
    name="backtest_exit_reason",
    create_type=False,
)


def upgrade() -> None:
    exit_reason.create(op.get_bind(), checkfirst=True)
    money = sa.Numeric(24, 8)
    op.create_table(
        "backtest_trades",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("signal_date", sa.Date(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry_price", money, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("exit_date", sa.Date(), nullable=False),
        sa.Column("exit_price", money, nullable=False),
        sa.Column("exit_reason", exit_reason, nullable=False),
        sa.Column("gross_pnl", money, nullable=False),
        sa.Column("commission", money, nullable=False),
        sa.Column("tax", money, nullable=False),
        sa.Column("slippage_cost", money, nullable=False),
        sa.Column("net_pnl", money, nullable=False),
        sa.Column("holding_days", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("signal_date < entry_date", name="signal_before_entry"),
        sa.CheckConstraint("exit_date >= entry_date", name="exit_after_entry"),
        sa.CheckConstraint("quantity > 0", name="positive_quantity"),
        sa.ForeignKeyConstraint(["run_id"], ["backtest_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "symbol", "signal_date", name="uq_backtest_trade_signal"),
    )
    for column in ("run_id", "symbol", "entry_date", "exit_date"):
        op.create_index(f"ix_backtest_trades_{column}", "backtest_trades", [column])


def downgrade() -> None:
    op.drop_table("backtest_trades")
    exit_reason.drop(op.get_bind(), checkfirst=True)
