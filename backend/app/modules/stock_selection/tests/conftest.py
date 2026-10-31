from pathlib import Path

import pytest
from sqlalchemy import text

from app.shared.database import create_engine_for_database, create_session_factory
from app.shared.migrations import migrate_database


@pytest.fixture
def candidate_store(tmp_path: Path):
    database = tmp_path / "stock-selection.db"
    migrate_database(database, backup_dir=tmp_path / "backups")
    engine = create_engine_for_database(database)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(username, password_hash, role, disabled, automation_state, automation_methods, created_at) "
                "VALUES ('module-test-user', 'unused', 'trader', 0, 'off', '[]', '2026-10-31T00:00:00Z')"
            )
        )
    yield create_session_factory(engine)
    engine.dispose()
