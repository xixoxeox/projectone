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
    connection = op.get_bind()
    duplicate_success_date = connection.execute(
        sa.text(
            """
            SELECT trading_date
            FROM watchlist_pipeline_executions
            WHERE status = 'succeeded'
            GROUP BY trading_date
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if duplicate_success_date is not None:
        raise RuntimeError(
            "Cannot downgrade watchlist reanalysis migration: multiple successful "
            f"executions exist for {duplicate_success_date}. Downgrade would violate "
            "preserved reanalysis audit history; explicitly resolve that history outside "
            "the migration before retrying."
        )
    op.drop_index("uq_watchlist_pipeline_running_date", table_name="watchlist_pipeline_executions")
    op.create_index(
        "uq_watchlist_pipeline_active_or_succeeded_date",
        "watchlist_pipeline_executions",
        ["trading_date"],
        unique=True,
        postgresql_where=sa.text("status IN ('running', 'succeeded')"),
    )
