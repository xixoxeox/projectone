"""Add durable daily watchlist pipeline execution history."""

import sqlalchemy as sa
from alembic import op

revision = "0004_watchlist_pipeline_executions"
down_revision = "0003_watchlist_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_pipeline_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("candidate_count", sa.Integer()),
        sa.Column("persisted_count", sa.Integer()),
        sa.Column("skipped_reason", sa.Text()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_detail", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_watchlist_pipeline_executions"),
    )
    op.create_index(
        "ix_watchlist_pipeline_executions_trading_date",
        "watchlist_pipeline_executions",
        ["trading_date"],
    )
    op.create_index(
        "ix_watchlist_pipeline_executions_status", "watchlist_pipeline_executions", ["status"]
    )
    op.create_index(
        "ix_watchlist_pipeline_executions_started_at",
        "watchlist_pipeline_executions",
        ["started_at"],
    )
    # This PostgreSQL partial index is the distributed ownership/idempotency primitive.
    op.create_index(
        "uq_watchlist_pipeline_active_or_succeeded_date",
        "watchlist_pipeline_executions",
        ["trading_date"],
        unique=True,
        postgresql_where=sa.text("status IN ('running', 'succeeded')"),
    )


def downgrade() -> None:
    op.drop_table("watchlist_pipeline_executions")
