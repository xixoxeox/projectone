"""Persist daily portfolio mark-to-market snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0007_backtest_portfolio_snapshots"
down_revision = "0006_backtest_trades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    money = sa.Numeric(24, 8)
    op.create_table(
        "backtest_portfolio_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("cash", money, nullable=False),
        sa.Column("market_value", money, nullable=False),
        sa.Column("realized_pnl", money, nullable=False),
        sa.Column("unrealized_pnl", money, nullable=False),
        sa.Column("total_equity", money, nullable=False),
        sa.Column("cumulative_return", money, nullable=False),
        sa.Column("running_peak_equity", money, nullable=False),
        sa.Column("drawdown", money, nullable=False),
        sa.Column("drawdown_pct", money, nullable=False),
        sa.Column("open_position_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("open_position_count >= 0", name="nonnegative_open_positions"),
        sa.ForeignKeyConstraint(["run_id"], ["backtest_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "trading_date", name="uq_portfolio_snapshot_run_date"),
    )
    op.create_index(
        "ix_backtest_portfolio_snapshots_run_id", "backtest_portfolio_snapshots", ["run_id"]
    )
    op.create_index(
        "ix_backtest_portfolio_snapshots_trading_date",
        "backtest_portfolio_snapshots",
        ["trading_date"],
    )


def downgrade() -> None:
    op.drop_table("backtest_portfolio_snapshots")
