"""Persist deduplicated deterministic exit-trigger audit records.

Revision ID: 008_position_monitoring
Revises: 007_execution
"""

from alembic import op
import sqlalchemy as sa

revision = "008_position_monitoring"
down_revision = "007_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "position_monitor_triggers" in inspector.get_table_names():
        return
    op.create_table(
        "position_monitor_triggers",
        sa.Column("trigger_id", sa.String(36), primary_key=True),
        sa.Column("position_id", sa.String(36), nullable=False),
        sa.Column("trigger_key", sa.String(128), nullable=False),
        sa.Column("trigger_reason", sa.String(32), nullable=False),
        sa.Column("policy_version", sa.String(32), nullable=False),
        sa.Column("trigger_price", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "trigger_reason IN ('STOP_LOSS', 'TARGET_REACHED', 'SESSION_SQUARE_OFF')",
            name="ck_position_monitor_trigger_reason",
        ),
        sa.UniqueConstraint("position_id", "trigger_key", name="uq_position_monitor_trigger"),
    )


def downgrade() -> None:
    # Keep monitoring audit records on rollback.
    pass
