"""Add backtest run lifecycle persistence."""

import sqlalchemy as sa
from alembic import op

revision = "0004_backtest_runs"
down_revision = "0003_watchlist_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = sa.Enum("pending", "running", "completed", "failed", name="backtest_status")
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_name", sa.String(100), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("parameters", sa.Text(), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint("start_date <= end_date", name="ck_backtest_runs_date_range"),
        sa.PrimaryKeyConstraint("id", name="pk_backtest_runs"),
    )
    op.create_index("ix_backtest_runs_created_at", "backtest_runs", ["created_at"])
    op.create_index("ix_backtest_runs_status", "backtest_runs", ["status"])
    op.create_index("ix_backtest_runs_strategy_name", "backtest_runs", ["strategy_name"])


def downgrade() -> None:
    op.drop_table("backtest_runs")
    sa.Enum(name="backtest_status").drop(op.get_bind(), checkfirst=True)
