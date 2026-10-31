"""Bring the three-table captured legacy core to the current runtime schema.

Revision ID: 002_legacy_runtime
Revises: 001_legacy_core
"""

from alembic import op
import sqlalchemy as sa

revision = "002_legacy_runtime"
down_revision = "001_legacy_core"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _require_complete_existing_table(table: str, required_columns: set[str]) -> None:
    columns = _columns(table)
    missing = required_columns - columns
    if missing:
        raise RuntimeError(
            f"Existing {table} table is incomplete; refusing to guess values for: {', '.join(sorted(missing))}"
        )


def upgrade() -> None:
    tables = _tables()
    user_columns = _columns("users")
    if "trading_index" not in user_columns:
        op.add_column("users", sa.Column("trading_index", sa.Text(), server_default="NIFTY 50", nullable=False))
    if "dhan_token_refreshed_at" not in user_columns:
        op.add_column("users", sa.Column("dhan_token_refreshed_at", sa.Text(), nullable=True))

    pending_columns = _columns("pending_orders")
    if "correlation_id" not in pending_columns:
        op.add_column("pending_orders", sa.Column("correlation_id", sa.Text(), nullable=True))
    if "broker_order_id" not in pending_columns:
        op.add_column("pending_orders", sa.Column("broker_order_id", sa.Text(), nullable=True))

    expected_existing = {
        "risk_settings": {
            "id", "max_positions", "capital_per_trade_pct", "cash_reserve_pct", "take_profit_pct",
            "stop_loss_pct", "max_daily_loss_inr", "screener_limit", "cycle_interval_seconds",
        },
        "dhan_process_credential": {"id", "access_token", "refreshed_at"},
        "protective_stops": {
            "id", "user_id", "symbol", "product", "quantity", "stop_order_id", "exit_side",
            "trigger_price", "status", "created_at",
        },
    }
    for table, columns in expected_existing.items():
        if table in tables:
            _require_complete_existing_table(table, columns)

    if "risk_settings" not in tables:
        op.create_table(
            "risk_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("max_positions", sa.Integer(), nullable=False),
            sa.Column("capital_per_trade_pct", sa.Float(), nullable=False),
            sa.Column("cash_reserve_pct", sa.Float(), nullable=False),
            sa.Column("take_profit_pct", sa.Float(), nullable=False),
            sa.Column("stop_loss_pct", sa.Float(), nullable=False),
            sa.Column("max_daily_loss_inr", sa.Float(), nullable=False),
            sa.Column("screener_limit", sa.Integer(), nullable=False),
            sa.Column("cycle_interval_seconds", sa.Integer(), nullable=False),
            sa.CheckConstraint("id = 1", name="ck_risk_settings_singleton"),
        )
    if "dhan_process_credential" not in tables:
        op.create_table(
            "dhan_process_credential",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("access_token", sa.Text(), nullable=False),
            sa.Column("refreshed_at", sa.Text(), nullable=False),
            sa.CheckConstraint("id = 1", name="ck_dhan_process_credential_singleton"),
        )
    if "protective_stops" not in tables:
        op.create_table(
            "protective_stops",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("symbol", sa.Text(), nullable=False),
            sa.Column("product", sa.Text(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("stop_order_id", sa.Text()),
            sa.Column("exit_side", sa.Text(), nullable=False),
            sa.Column("trigger_price", sa.Float(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
        )


def downgrade() -> None:
    # Runtime tables and columns are additive. Downgrading would risk current data.
    pass
