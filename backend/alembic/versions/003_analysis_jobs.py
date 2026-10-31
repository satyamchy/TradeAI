"""Add the durable idempotent analysis-job queue."""

from alembic import op
import sqlalchemy as sa

revision = "003_analysis_jobs"
down_revision = "002_legacy_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "analysis_jobs" in inspector.get_table_names():
        required = {
            "analysis_id", "created_by_user_id", "idempotency_key", "status", "request_json",
            "result_reference", "failure_code", "failure_message", "attempt_count", "max_attempts",
            "retryable", "created_at", "updated_at", "started_at", "completed_at",
        }
        actual = {column["name"] for column in inspector.get_columns("analysis_jobs")}
        missing = required - actual
        if missing:
            raise RuntimeError(
                "Existing analysis_jobs table does not match the Phase 1 job contract; "
                "refusing to overwrite or silently skip it. Missing: " + ", ".join(sorted(missing))
            )
        return
    op.create_table(
        "analysis_jobs",
        sa.Column("analysis_id", sa.String(length=36), primary_key=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("request_json", sa.Text(), nullable=False),
        sa.Column("result_reference", sa.String(length=500), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.String(length=500), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_analysis_jobs_status",
        ),
        sa.CheckConstraint("attempt_count >= 0 AND max_attempts >= 1", name="ck_analysis_jobs_attempts"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("created_by_user_id", "idempotency_key", name="uq_analysis_jobs_owner_idempotency"),
    )
    op.create_index("ix_analysis_jobs_status_created_at", "analysis_jobs", ["status", "created_at"])


def downgrade() -> None:
    # Keep durable job history during a rollback; the migration is additive.
    pass
