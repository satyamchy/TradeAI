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
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the tables if they are missing."""
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def _user(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    data["disabled"] = bool(data["disabled"])
    data["dhan_saved"] = bool(data.get("dhan_access_token"))
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
    """Store ciphertext. The caller encrypts."""
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET dhan_client_id = ?, dhan_access_token = ? WHERE id = ?",
            (client_id_enc, token_enc, user_id),
        )


def set_automation(user_id: int, state: str, methods_json: str) -> None:
    """`state` is off, entries, or exits_only."""
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET automation_state = ?, automation_methods = ? WHERE id = ?",
            (state, methods_json, user_id),
        )


def traders_to_run() -> list[dict]:
    """Traders the loop should visit: entries on, or exits still to manage."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM users
            WHERE disabled = 0 AND role = 'trader' AND automation_state IN ('entries', 'exits_only')
            ORDER BY id
            """
        ).fetchall()
    return [_user(row) for row in rows]


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
            WHERE user_id = ? AND status = 'pending'
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
