"""add durable daily pipeline execution history

Revision ID: 0004_pipeline_executions
Revises: 0003_watchlist_entries
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_pipeline_executions"
down_revision = "0003_watchlist_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("persisted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(30)),
        sa.Column("error_code", sa.String(255)),
        sa.Column("recovered_execution_id", sa.Uuid()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_executions")),
        sa.UniqueConstraint("trading_date", "owner_id", name="uq_pipeline_execution_owner"),
    )
    op.create_index(op.f("ix_pipeline_executions_status"), "pipeline_executions", ["status"])
    op.create_index(
        op.f("ix_pipeline_executions_trading_date"), "pipeline_executions", ["trading_date"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_pipeline_executions_trading_date"), table_name="pipeline_executions")
    op.drop_index(op.f("ix_pipeline_executions_status"), table_name="pipeline_executions")
    op.drop_table("pipeline_executions")
