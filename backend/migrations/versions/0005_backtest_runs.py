"""Add backtest run lifecycle persistence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_backtest_runs"
down_revision = "0004_watchlist_pipeline_exec"
branch_labels = None
depends_on = None

backtest_status = postgresql.ENUM(
    "pending", "running", "completed", "failed", name="backtest_status", create_type=False
)


def upgrade() -> None:
    backtest_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_name", sa.String(100), nullable=False),
        sa.Column("strategy_version", sa.String(100), nullable=True),
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("data_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", backtest_status, nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("start_date <= end_date", name="ck_backtest_runs_date_range"),
        sa.PrimaryKeyConstraint("id", name="pk_backtest_runs"),
    )
    op.create_index("ix_backtest_runs_created_at", "backtest_runs", ["created_at"])
    op.create_index("ix_backtest_runs_status", "backtest_runs", ["status"])
    op.create_index("ix_backtest_runs_strategy_name", "backtest_runs", ["strategy_name"])


def downgrade() -> None:
    op.drop_table("backtest_runs")
    backtest_status.drop(op.get_bind(), checkfirst=True)
