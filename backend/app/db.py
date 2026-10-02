"""SQLite tables for users, pending orders, and the event log.

This is the only database. Passwords stored here are already hashed.
Dhan tokens stored here are already encrypted. This module does not
place orders.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings

IST = ZoneInfo("Asia/Kolkata")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 0,
    dhan_client_id TEXT,
    dhan_access_token TEXT,
    automation_state TEXT NOT NULL DEFAULT 'off',
    automation_methods TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    action TEXT NOT NULL,
    symbol TEXT,
    side TEXT,
    quantity INTEGER,
    product TEXT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS risk_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    max_positions INTEGER NOT NULL,
    capital_per_trade_pct REAL NOT NULL,
    cash_reserve_pct REAL NOT NULL,
    take_profit_pct REAL NOT NULL,
    stop_loss_pct REAL NOT NULL,
    max_daily_loss_inr REAL NOT NULL,
    screener_limit INTEGER NOT NULL,
    cycle_interval_seconds INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dhan_process_credential (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    access_token TEXT NOT NULL,
    refreshed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS protective_stops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    product TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    stop_order_id TEXT,
    exit_side TEXT NOT NULL,
    trigger_price REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _db_path() -> str:
    return _resolve_path(settings.database_path)


def _resolve_path(path: str) -> str:
    from pathlib import Path

    candidate = Path(path)
    if candidate.is_absolute():
        return str(candidate)
    return str(Path(__file__).resolve().parents[1] / candidate)


def init_db() -> None:
    """Create the tables if they are missing, then add columns from later versions."""
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "trading_index" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN trading_index TEXT NOT NULL DEFAULT 'NIFTY 50'")
    pending_cols = {row[1] for row in conn.execute("PRAGMA table_info(pending_orders)")}
    if "correlation_id" not in pending_cols:
        conn.execute("ALTER TABLE pending_orders ADD COLUMN correlation_id TEXT")
    if "broker_order_id" not in pending_cols:
        conn.execute("ALTER TABLE pending_orders ADD COLUMN broker_order_id TEXT")
    if "dhan_token_refreshed_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN dhan_token_refreshed_at TEXT")


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def _user(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    data["disabled"] = bool(data["disabled"])
    data["dhan_saved"] = bool(data.get("dhan_access_token"))
    data["trading_index"] = data.get("trading_index") or "NIFTY 50"
    return data


def create_user(username: str, password_hash: str, role: str) -> dict:
    """Insert a user. `password_hash` is stored as given."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (username, password_hash, role, _now()),
        )
        user_id = cur.lastrowid
    return get_user(user_id)


def get_user(user_id: int) -> dict | None:
    """One user by id, or None."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user(row)


def get_user_by_username(username: str) -> dict | None:
    """One user by login name, or None."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return _user(row)


def list_users() -> list[dict]:
    """Every account, oldest first. Token ciphertext is not included."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    public = []
    for row in rows:
        user = _user(row)
        user.pop("password_hash", None)
        user.pop("dhan_client_id", None)
        user.pop("dhan_access_token", None)
        public.append(user)
    return public


def user_count() -> int:
    """How many accounts exist."""
    with _connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def update_user(user_id: int, *, role: str | None = None, disabled: bool | None = None) -> dict | None:
    """Change role or disabled. Omitted fields stay as they are."""
    user = get_user(user_id)
    if user is None:
        return None
    next_role = role if role is not None else user["role"]
    next_disabled = int(disabled) if disabled is not None else int(user["disabled"])
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET role = ?, disabled = ? WHERE id = ?",
            (next_role, next_disabled, user_id),
        )
    return get_user(user_id)


def save_dhan_credentials(user_id: int, client_id_enc: str, token_enc: str) -> None:
    """Store ciphertext and start the 24-hour renewal clock. The caller encrypts."""
    with _connect() as conn:
        conn.execute(
            """
            UPDATE users
            SET dhan_client_id = ?, dhan_access_token = ?, dhan_token_refreshed_at = ?
            WHERE id = ?
            """,
            (client_id_enc, token_enc, _now(), user_id),
        )


def get_process_dhan_token() -> dict | None:
    """The last renewed process token, or None before the first renewal."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM dhan_process_credential WHERE id = 1").fetchone()
    return dict(row) if row else None


def save_process_dhan_token(token_enc: str) -> None:
    """Store the renewed process token ciphertext."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO dhan_process_credential (id, access_token, refreshed_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                access_token = excluded.access_token,
                refreshed_at = excluded.refreshed_at
            """,
            (token_enc, _now()),
        )


def list_dhan_traders() -> list[dict]:
    """Traders who have a saved Dhan token, including a disabled account still flattening."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM users
            WHERE role = 'trader'
              AND dhan_access_token IS NOT NULL
              AND dhan_access_token != ''
            ORDER BY id
            """
        ).fetchall()
    return [_user(row) for row in rows]


def set_automation(user_id: int, state: str, methods_json: str) -> None:
    """`state` is off, entries, or exits_only."""
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET automation_state = ?, automation_methods = ? WHERE id = ?",
            (state, methods_json, user_id),
        )


def traders_to_run() -> list[dict]:
    """Traders the loop should visit: entries on, or exits still to manage.

    A disabled account, or one that is no longer a trader, stays in the loop
    while its state is exits_only so open intraday risk is still flattened.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM users
            WHERE automation_state IN ('entries', 'exits_only')
              AND (
                    (disabled = 0 AND role = 'trader')
                 OR automation_state = 'exits_only'
              )
            ORDER BY id
            """
        ).fetchall()
    return [_user(row) for row in rows]


def set_trading_index(user_id: int, index_name: str) -> None:
    """Remember which NSE index this trader's entries come from."""
    with _connect() as conn:
        conn.execute("UPDATE users SET trading_index = ? WHERE id = ?", (index_name, user_id))


def claim_pending(pending_id: int, user_id: int, correlation_id: str) -> dict | None:
    """Move a pending row to executing. None when another request already claimed it."""
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE pending_orders
            SET status = 'executing', correlation_id = ?
            WHERE id = ? AND user_id = ? AND status = 'pending'
            """,
            (correlation_id, pending_id, user_id),
        )
        if cur.rowcount != 1:
            return None
    return get_pending(pending_id)


def set_pending_broker(pending_id: int, broker_order_id: str) -> None:
    """Store the broker order id while the row is still executing."""
    with _connect() as conn:
        conn.execute(
            "UPDATE pending_orders SET broker_order_id = ? WHERE id = ?",
            (broker_order_id, pending_id),
        )


def list_executing() -> list[dict]:
    """Rows that were sent, or might have been sent, and are not finished."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM pending_orders WHERE status = 'executing' ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def get_risk_settings() -> dict | None:
    """The shared limits last saved by an admin, or None before the first save."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM risk_settings WHERE id = 1").fetchone()
    if row is None:
        return None
    return dict(row)


def save_risk_settings(values: dict) -> dict:
    """Replace the single shared limits row."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO risk_settings (
                id, max_positions, capital_per_trade_pct, cash_reserve_pct,
                take_profit_pct, stop_loss_pct, max_daily_loss_inr,
                screener_limit, cycle_interval_seconds
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                max_positions = excluded.max_positions,
                capital_per_trade_pct = excluded.capital_per_trade_pct,
                cash_reserve_pct = excluded.cash_reserve_pct,
                take_profit_pct = excluded.take_profit_pct,
                stop_loss_pct = excluded.stop_loss_pct,
                max_daily_loss_inr = excluded.max_daily_loss_inr,
                screener_limit = excluded.screener_limit,
                cycle_interval_seconds = excluded.cycle_interval_seconds
            """,
            (
                int(values["max_positions"]),
                float(values["capital_per_trade_pct"]),
                float(values["cash_reserve_pct"]),
                float(values["take_profit_pct"]),
                float(values["stop_loss_pct"]),
                float(values["max_daily_loss_inr"]),
                int(values["screener_limit"]),
                int(values["cycle_interval_seconds"]),
            ),
        )
    saved = get_risk_settings()
    assert saved is not None
    return saved


def add_protective_stop(
    user_id: int,
    symbol: str,
    product: str,
    quantity: int,
    stop_order_id: str | None,
    exit_side: str,
    trigger_price: float,
) -> None:
    """Remember a broker stop so an exit can cancel it before selling again."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO protective_stops
                (user_id, symbol, product, quantity, stop_order_id, exit_side, trigger_price, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'working', ?)
            """,
            (user_id, symbol, product, quantity, stop_order_id, exit_side, trigger_price, _now()),
        )


def working_stops(user_id: int, symbol: str, product: str) -> list[dict]:
    """Working protective stops for one symbol and product."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM protective_stops
            WHERE user_id = ? AND symbol = ? AND product = ? AND status = 'working'
            ORDER BY id
            """,
            (user_id, symbol, product),
        ).fetchall()
    return [dict(row) for row in rows]


def finish_stop(stop_id: int, status: str) -> None:
    """Mark a protective stop cancelled or filled."""
    with _connect() as conn:
        conn.execute("UPDATE protective_stops SET status = ? WHERE id = ?", (status, stop_id))


def add_pending(
    user_id: int,
    source: str,
    product: str,
    symbol: str,
    side: str,
    quantity: int,
    price: float,
    detail: str,
) -> dict:
    """Save a suggestion or delivery request. Status starts at pending."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO pending_orders
                (user_id, source, product, symbol, side, quantity, price, status, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (user_id, source, product, symbol, side, quantity, price, detail, _now()),
        )
        pending_id = cur.lastrowid
    return get_pending(pending_id)


def get_pending(pending_id: int) -> dict | None:
    """One pending row, or None."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM pending_orders WHERE id = ?", (pending_id,)).fetchone()
    return dict(row) if row else None


def list_pending(user_id: int) -> list[dict]:
    """Pending rows for one user, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM pending_orders
            WHERE user_id = ? AND status IN ('pending', 'executing')
            ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def set_pending_status(pending_id: int, status: str) -> None:
    """Mark a row executed or rejected."""
    with _connect() as conn:
        conn.execute("UPDATE pending_orders SET status = ? WHERE id = ?", (status, pending_id))


def add_event(
    user_id: int,
    action: str,
    status: str,
    *,
    symbol: str | None = None,
    side: str | None = None,
    quantity: int | None = None,
    product: str | None = None,
    detail: str = "",
) -> None:
    """Append one audit row. Do not put secrets in `detail`."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO order_events
                (user_id, created_at, action, symbol, side, quantity, product, mode, status, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                _now(),
                action,
                symbol,
                side,
                quantity,
                product,
                settings.trading_mode.strip().lower(),
                status,
                detail[:500],
            ),
        )


def list_events(user_id: int | None, limit: int = 100) -> list[dict]:
    """Newest events. `user_id` None returns every account, for an admin."""
    with _connect() as conn:
        if user_id is None:
            rows = conn.execute(
                "SELECT * FROM order_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM order_events WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
    return [dict(row) for row in rows]
