CREATE TABLE users (
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
CREATE TABLE pending_orders (
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
CREATE TABLE order_events (
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
INSERT INTO users (username, password_hash, role, created_at) VALUES
    ('fixture-admin', 'not-a-real-password-hash', 'admin', '2026-01-01T00:00:00+00:00'),
    ('fixture-trader', 'not-a-real-password-hash', 'trader', '2026-01-02T00:00:00+00:00');
INSERT INTO pending_orders (user_id, source, product, symbol, side, quantity, price, status, detail, created_at)
VALUES (2, 'manual', 'DELIVERY', 'TESTCO', 'BUY', 1, 100.0, 'pending', '', '2026-01-02T00:00:00+00:00');
INSERT INTO order_events (user_id, created_at, action, mode, status, detail)
VALUES (2, '2026-01-02T00:00:00+00:00', 'baseline', 'paper', 'ok', 'fixture');
