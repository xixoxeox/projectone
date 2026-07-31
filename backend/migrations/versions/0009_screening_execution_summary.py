"""Record the screening funnel and score threshold for explainable empty results."""

import sqlalchemy as sa
from alembic import op

revision = "0009_screening_summary"
down_revision = "0008_watchlist_reanalysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "watchlist_pipeline_executions",
        sa.Column("screened_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "watchlist_pipeline_executions",
        sa.Column("qualified_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "watchlist_pipeline_executions",
        sa.Column("score_threshold", sa.Numeric(5, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("watchlist_pipeline_executions", "score_threshold")
    op.drop_column("watchlist_pipeline_executions", "qualified_count")
    op.drop_column("watchlist_pipeline_executions", "screened_count")
