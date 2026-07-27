"""Add normalized market persistence and synchronization audit tables."""

import sqlalchemy as sa
from alembic import op

revision = "0002_market_persistence"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stocks",
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("market", sa.String(30), nullable=False),
        sa.Column("exchange", sa.String(50)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("security_type", sa.String(30)),
        sa.Column("listing_status", sa.String(30)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("symbol", name="pk_stocks"),
    )
    op.create_index("ix_stocks_market", "stocks", ["market"])
    op.create_index("ix_stocks_is_active", "stocks", ["is_active"])
    op.create_table(
        "daily_bars",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(20, 6), nullable=False),
        sa.Column("high", sa.Numeric(20, 6), nullable=False),
        sa.Column("low", sa.Numeric(20, 6), nullable=False),
        sa.Column("close", sa.Numeric(20, 6), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("provider_timestamp", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "open >= 0 AND high >= 0 AND low >= 0 AND close >= 0 AND volume >= 0",
            name="ck_daily_bars_non_negative",
        ),
        sa.CheckConstraint(
            "high >= open AND high >= close AND high >= low AND low <= open AND low <= close",
            name="ck_daily_bars_valid_ohlc",
        ),
        sa.ForeignKeyConstraint(
            ["symbol"], ["stocks.symbol"], name="fk_daily_bars_symbol_stocks", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_daily_bars"),
        sa.UniqueConstraint("symbol", "trading_date", name="uq_daily_bars_symbol_date"),
    )
    op.create_index("ix_daily_bars_symbol", "daily_bars", ["symbol"])
    op.create_index("ix_daily_bars_trading_date", "daily_bars", ["trading_date"])
    op.create_table(
        "sync_jobs",
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_at", sa.DateTime(timezone=True)),
        sa.Column("last_cursor", sa.String(255)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("name", name="pk_sync_jobs"),
    )
    op.create_table(
        "sync_job_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_name", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.BigInteger()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("inserted_rows", sa.Integer(), nullable=False),
        sa.Column("updated_rows", sa.Integer(), nullable=False),
        sa.Column("skipped_rows", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.ForeignKeyConstraint(
            ["job_name"],
            ["sync_jobs.name"],
            name="fk_sync_job_runs_job_name_sync_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sync_job_runs"),
    )
    op.create_index("ix_sync_job_runs_job_name", "sync_job_runs", ["job_name"])
    op.create_index("ix_sync_job_runs_status", "sync_job_runs", ["status"])


def downgrade() -> None:
    op.drop_table("sync_job_runs")
    op.drop_table("sync_jobs")
    op.drop_table("daily_bars")
    op.drop_table("stocks")
