"""Allow historical successes while retaining one active run per date."""

import sqlalchemy as sa
from alembic import op

revision = "0008_watchlist_reanalysis"
down_revision = "0007_portfolio_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        "uq_watchlist_pipeline_active_or_succeeded_date", table_name="watchlist_pipeline_executions"
    )
    op.create_index(
        "uq_watchlist_pipeline_running_date",
        "watchlist_pipeline_executions",
        ["trading_date"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_watchlist_pipeline_running_date", table_name="watchlist_pipeline_executions")
    op.create_index(
        "uq_watchlist_pipeline_active_or_succeeded_date",
        "watchlist_pipeline_executions",
        ["trading_date"],
        unique=True,
        postgresql_where=sa.text("status IN ('running', 'succeeded')"),
    )
