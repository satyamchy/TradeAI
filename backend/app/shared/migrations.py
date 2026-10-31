"""Safe Alembic adoption/upgrade helpers for the legacy SQLite database."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.shared.database import database_url

BASE_REVISION = "001_legacy_core"
HEAD_REVISION = "008_position_monitoring"
CORE_TABLE_COLUMNS = {
    "users": {
        "id", "username", "password_hash", "role", "disabled", "dhan_client_id",
        "dhan_access_token", "automation_state", "automation_methods", "created_at",
    },
    "pending_orders": {
        "id", "user_id", "source", "product", "symbol", "side", "quantity", "price",
        "status", "detail", "created_at",
    },
    "order_events": {
        "id", "user_id", "created_at", "action", "symbol", "side", "quantity",
        "product", "mode", "status", "detail",
    },
}


class UnrecognizedLegacyDatabase(RuntimeError):
    """An unversioned database doesn't match the known, safe adoption shape."""


def migrate_database(
    database_path: str | Path,
    *,
    backup_dir: str | Path,
    alembic_ini: str | Path | None = None,
) -> Path | None:
    """Migrate a fresh database or safely adopt the captured legacy schema.

    A non-empty unversioned database is backed up before it is stamped or
    upgraded. Its three core tables and minimum columns are checked first.
    The original database file path is always used for migration.
    """
    path = Path(database_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    path.parent.mkdir(parents=True, exist_ok=True)

    ini_path = Path(alembic_ini) if alembic_ini else Path(__file__).resolve().parents[2] / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(ini_path.parent / "alembic").replace("%", "%%"))
    url = database_url(path).render_as_string(hide_password=False)
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

    backup_path: Path | None = None
    exists = path.exists() and path.stat().st_size > 0
    tables = _sqlite_tables(path) if exists else set()
    if exists and tables:
        current_revision = _alembic_revision(path)
        if current_revision is None:
            _validate_legacy_core(path, tables)
            backup_path = _backup_database(path, Path(backup_dir))
            command.stamp(cfg, BASE_REVISION)
        elif current_revision != HEAD_REVISION:
            backup_path = _backup_database(path, Path(backup_dir))
        else:
            return None

    command.upgrade(cfg, "head")
    return backup_path


def _sqlite_tables(path: Path) -> set[str]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }


def _alembic_revision(path: Path) -> str | None:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        if "alembic_version" not in _sqlite_tables(path):
            return None
        row = connection.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
        return str(row[0]) if row else None


def _validate_legacy_core(path: Path, tables: set[str]) -> None:
    missing_tables = set(CORE_TABLE_COLUMNS) - tables
    if missing_tables:
        raise UnrecognizedLegacyDatabase(
            "Unversioned database is missing required legacy tables: " + ", ".join(sorted(missing_tables))
        )
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        for table, required in CORE_TABLE_COLUMNS.items():
            actual = {
                row[1]
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            }
            missing = required - actual
            if missing:
                raise UnrecognizedLegacyDatabase(
                    f"Unversioned database table {table!r} is missing required columns: {', '.join(sorted(missing))}"
                )
        username_unique = False
        for index in connection.execute('PRAGMA index_list("users")'):
            if not index[2]:
                continue
            indexed_columns = [
                row[2]
                for row in connection.execute(f'PRAGMA index_info("{index[1]}")')
            ]
            if indexed_columns == ["username"]:
                username_unique = True
                break
        if not username_unique:
            raise UnrecognizedLegacyDatabase("Unversioned database is missing the unique users.username constraint")


def _backup_database(source: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = backup_dir / f"{source.stem}-pre-migration-{stamp}.db"
    temporary = target.with_suffix(".tmp")
    try:
        src = sqlite3.connect(source)
        dst = sqlite3.connect(temporary)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target
