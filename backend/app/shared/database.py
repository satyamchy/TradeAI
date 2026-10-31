"""Injected SQLAlchemy 2.x database/session infrastructure."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import URL, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Metadata base for new SQLAlchemy-owned tables."""


def database_url(database_path: str | Path) -> URL:
    """Build a portable SQLite URL from the configured legacy database path."""
    raw = str(database_path)
    if "://" in raw:
        return make_url(raw)
    path = Path(raw)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return URL.create("sqlite", database=str(path))


def create_engine_for_database(database_path: str | Path, **options: Any) -> Engine:
    """Create one engine. No schema is created implicitly."""
    url = database_url(database_path)
    connect_args: dict[str, Any] = {}
    if url.get_backend_name() == "sqlite":
        connect_args = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True, **options)

    if url.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_connection_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return an injected session factory with explicit transaction scopes."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
