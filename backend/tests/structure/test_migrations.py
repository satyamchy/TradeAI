import sqlite3
from pathlib import Path

import pytest

from app.shared.migrations import HEAD_REVISION, migrate_database


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "legacy_three_table.sql"


def _create_legacy_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(FIXTURE.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def test_fresh_sqlite_initialization_runs_all_revisions(tmp_path):
    database = tmp_path / "fresh.db"

    backup = migrate_database(database, backup_dir=tmp_path / "backups")

    assert backup is None
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD_REVISION
        assert {"users", "pending_orders", "order_events", "risk_settings", "dhan_process_credential", "protective_stops", "analysis_jobs"} <= _tables(connection)
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_list(analysis_jobs)").fetchone()[2] == "users"
    finally:
        connection.close()


def test_existing_database_copy_is_backed_up_and_preserved(tmp_path):
    database = tmp_path / "existing-copy.db"
    _create_legacy_db(database)
    backup_dir = tmp_path / "backups"

    backup = migrate_database(database, backup_dir=backup_dir)

    assert backup is not None and backup.is_file()
    with sqlite3.connect(backup) as saved:
        assert {table for table in ("users", "pending_orders", "order_events")} <= _tables(saved)
        assert saved.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
        assert "analysis_jobs" not in _tables(saved)
    with sqlite3.connect(database) as upgraded:
        assert upgraded.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD_REVISION
        assert upgraded.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
        assert upgraded.execute("SELECT COUNT(*) FROM pending_orders").fetchone()[0] == 1
        assert upgraded.execute("SELECT COUNT(*) FROM order_events").fetchone()[0] == 1
        assert upgraded.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert list(upgraded.execute("PRAGMA foreign_key_check")) == []
        with pytest.raises(sqlite3.IntegrityError):
            upgraded.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                ("fixture-admin", "hash", "admin", "2026-01-03T00:00:00+00:00"),
            )
