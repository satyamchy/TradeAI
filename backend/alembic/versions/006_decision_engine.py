"""Persist deterministic decisions and Module 3 approved intents.

Revision ID: 006_decision_engine
Revises: 005_ai_analysis
"""

from alembic import op
import sqlalchemy as sa

revision = "006_decision_engine"
down_revision = "005_ai_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    expected = {"trade_decisions", "approved_order_intents"}
    if expected <= existing:
        return
    if expected & existing:
        raise RuntimeError("Partial Module 3 schema detected; refusing to create a second decision schema")

    op.create_table(
        "trade_decisions",
        sa.Column("decision_id", sa.String(36), primary_key=True),
        sa.Column("decision_key", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("analysis_id", sa.String(36), nullable=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("strategy_key", sa.String(64), nullable=False),
        sa.Column("strategy_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('BUY_APPROVED', 'HOLD', 'REJECTED', 'SELL_APPROVED', 'REVIEW_REQUIRED')",
            name="ck_trade_decisions_status",
        ),
        sa.UniqueConstraint("decision_key", name="uq_trade_decisions_decision_key"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_trade_decisions_owner_created", "trade_decisions", ["owner_id", "created_at"])
    op.create_table(
        "approved_order_intents",
        sa.Column("order_intent_id", sa.String(36), primary_key=True),
        sa.Column("decision_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("intent_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('APPROVED', 'CONSUMED', 'EXPIRED')", name="ck_order_intents_status"),
        sa.UniqueConstraint("decision_id", name="uq_order_intents_decision"),
        sa.UniqueConstraint("idempotency_key", name="uq_order_intents_idempotency"),
        sa.ForeignKeyConstraint(["decision_id"], ["trade_decisions.decision_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    # Decision and intent records are audit data; retain them on rollback.
    pass
