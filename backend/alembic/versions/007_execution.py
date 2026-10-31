"""Persist broker-neutral order execution state and reconciliation history.

Revision ID: 007_execution
Revises: 006_decision_engine
"""

from alembic import op
import sqlalchemy as sa

revision = "007_execution"
down_revision = "006_decision_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    expected = {"execution_orders", "execution_order_events"}
    if expected <= existing:
        return
    if expected & existing:
        raise RuntimeError("Partial Module 4 schema detected; refusing to create duplicate execution tables")

    op.create_table(
        "execution_orders",
        sa.Column("tradeai_order_id", sa.String(36), primary_key=True),
        sa.Column("order_intent_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("broker", sa.String(32), nullable=False),
        sa.Column("broker_order_id", sa.String(128), nullable=True),
        sa.Column("execution_mode", sa.String(8), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("requested_quantity", sa.Integer(), nullable=False),
        sa.Column("filled_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remaining_quantity", sa.Integer(), nullable=False),
        sa.Column("average_fill_price", sa.String(32), nullable=True),
        sa.Column("rejection_reason", sa.String(256), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('CREATED', 'SUBMITTED', 'PENDING', 'OPEN', 'PARTIALLY_FILLED', "
            "'FILLED', 'REJECTED', 'CANCELLED', 'UNKNOWN')",
            name="ck_execution_orders_status",
        ),
        sa.CheckConstraint("filled_quantity >= 0 AND remaining_quantity >= 0", name="ck_execution_orders_quantities"),
        sa.UniqueConstraint("idempotency_key", name="uq_execution_orders_idempotency"),
    )
    op.create_index("ix_execution_orders_owner_status", "execution_orders", ["owner_id", "status"])
    op.create_table(
        "execution_order_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("tradeai_order_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("filled_quantity", sa.Integer(), nullable=False),
        sa.Column("remaining_quantity", sa.Integer(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tradeai_order_id"], ["execution_orders.tradeai_order_id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_execution_order_events_order_time", "execution_order_events", ["tradeai_order_id", "occurred_at"]
    )


def downgrade() -> None:
    # Keep broker audit history when changing application revisions.
    pass
