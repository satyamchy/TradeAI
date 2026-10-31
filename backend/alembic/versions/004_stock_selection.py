"""Persist manual stock-selection batches and instrument mappings.

Revision ID: 004_stock_selection
Revises: 003_analysis_jobs
"""

from alembic import op
import sqlalchemy as sa

revision = "004_stock_selection"
down_revision = "003_analysis_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "candidate_batches" not in tables:
        op.create_table(
            "candidate_batches",
            sa.Column("batch_id", sa.String(length=36), primary_key=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("selection_mode", sa.String(length=24), nullable=False),
            sa.Column("exchange", sa.String(length=16), nullable=False),
            sa.Column("horizon", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("submitted_symbols_json", sa.Text(), nullable=False),
            sa.Column("rejected_symbols_json", sa.Text(), nullable=False),
            sa.Column("rejections_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("selection_mode IN ('MANUAL')", name="ck_candidate_batches_selection_mode"),
            sa.CheckConstraint(
                "status IN ('COMPLETED', 'PARTIAL', 'REJECTED')",
                name="ck_candidate_batches_status",
            ),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index(
            "ix_candidate_batches_owner_created_at",
            "candidate_batches",
            ["created_by_user_id", "created_at"],
        )

    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "stock_candidates" not in tables:
        op.create_table(
            "stock_candidates",
            sa.Column("candidate_id", sa.String(length=36), primary_key=True),
            sa.Column("batch_id", sa.String(length=36), nullable=False),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("exchange", sa.String(length=16), nullable=False),
            sa.Column("trading_symbol", sa.String(length=32), nullable=True),
            sa.Column("analysis_ticker", sa.String(length=64), nullable=True),
            sa.Column("security_id", sa.String(length=64), nullable=True),
            sa.Column("segment", sa.String(length=16), nullable=True),
            sa.Column("currency", sa.String(length=8), nullable=False),
            sa.Column("selection_mode", sa.String(length=24), nullable=False),
            sa.Column("selection_reason", sa.String(length=64), nullable=False),
            sa.Column("validation_status", sa.String(length=16), nullable=False),
            sa.Column("mapping_source", sa.String(length=64), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("selection_mode IN ('MANUAL')", name="ck_stock_candidates_selection_mode"),
            sa.CheckConstraint(
                "validation_status IN ('VALID', 'ANALYSIS_ONLY')",
                name="ck_stock_candidates_validation_status",
            ),
            sa.ForeignKeyConstraint(["batch_id"], ["candidate_batches.batch_id"], ondelete="CASCADE"),
            sa.UniqueConstraint("batch_id", "symbol", name="uq_stock_candidates_batch_symbol"),
        )
        op.create_index("ix_stock_candidates_batch_id", "stock_candidates", ["batch_id"])
        op.create_index(
            "ix_stock_candidates_symbol_exchange", "stock_candidates", ["symbol", "exchange"]
        )


def downgrade() -> None:
    # Keep candidate audit history on rollback. The migration is additive.
    pass
