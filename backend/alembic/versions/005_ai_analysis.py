"""Persist provider-neutral analysis run configuration and results.

Revision ID: 005_ai_analysis
Revises: 004_stock_selection
"""

from alembic import op
import sqlalchemy as sa

revision = "005_ai_analysis"
down_revision = "004_stock_selection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "analysis_runs" in tables:
        required = {
            "analysis_id", "candidate_id", "provider", "provider_version", "profile_key",
            "profile_version", "status", "run_config_json", "result_json", "created_at",
            "started_at", "completed_at",
        }
        actual = {column["name"] for column in inspector.get_columns("analysis_runs")}
        missing = required - actual
        if missing:
            raise RuntimeError(
                "Existing analysis_runs table does not match the Module 2 contract; "
                "refusing to overwrite or silently skip it. Missing: " + ", ".join(sorted(missing))
            )
        return
    op.create_table(
        "analysis_runs",
        sa.Column("analysis_id", sa.String(length=36), primary_key=True),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_version", sa.String(length=32), nullable=False),
        sa.Column("profile_key", sa.String(length=64), nullable=False),
        sa.Column("profile_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("run_config_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_analysis_runs_status",
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["analysis_jobs.analysis_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["stock_candidates.candidate_id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_analysis_runs_candidate_created_at", "analysis_runs", ["candidate_id", "created_at"]
    )


def downgrade() -> None:
    # Keep analysis and research audit data on rollback.
    pass
