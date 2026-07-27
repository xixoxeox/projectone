"""Add persistent ranked watchlist entries."""

import sqlalchemy as sa
from alembic import op

revision = "0003_watchlist_entries"
down_revision = "0002_market_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("total_score", sa.Text(), nullable=False),
        sa.Column("component_scores", sa.Text(), nullable=False),
        sa.Column("warnings", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_watchlist_entries"),
        sa.UniqueConstraint("trading_date", "rank", name="uq_watchlist_entries_date_rank"),
        sa.UniqueConstraint("trading_date", "symbol", name="uq_watchlist_entries_date_symbol"),
    )
    op.create_index("ix_watchlist_entries_trading_date", "watchlist_entries", ["trading_date"])


def downgrade() -> None:
    op.drop_table("watchlist_entries")
