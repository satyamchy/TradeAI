"""Baseline for the three tables present in the captured legacy SQLite DB.

Revision ID: 001_legacy_core
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "001_legacy_core"
down_revision = None
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("username", sa.Text(), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("role", sa.Text(), nullable=False),
            sa.Column("disabled", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("dhan_client_id", sa.Text()),
            sa.Column("dhan_access_token", sa.Text()),
            sa.Column("automation_state", sa.Text(), server_default=sa.text("'off'"), nullable=False),
            sa.Column("automation_methods", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("username", name="uq_users_username"),
        )
    if "pending_orders" not in tables:
        op.create_table(
            "pending_orders",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("source", sa.Text(), nullable=False),
            sa.Column("product", sa.Text(), nullable=False),
            sa.Column("symbol", sa.Text(), nullable=False),
            sa.Column("side", sa.Text(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("price", sa.Float(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("detail", sa.Text(), server_default=sa.text("''"), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
        )
    if "order_events" not in tables:
        op.create_table(
            "order_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("action", sa.Text(), nullable=False),
            sa.Column("symbol", sa.Text()),
            sa.Column("side", sa.Text()),
            sa.Column("quantity", sa.Integer()),
            sa.Column("product", sa.Text()),
            sa.Column("mode", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("detail", sa.Text(), server_default=sa.text("''"), nullable=False),
        )


def downgrade() -> None:
    # The baseline represents user data. It is intentionally non-destructive.
    pass
