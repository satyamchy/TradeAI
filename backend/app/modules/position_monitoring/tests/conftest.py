from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.modules.position_monitoring.models import PositionTriggerRecord
from app.modules.position_monitoring.repository import SqlAlchemyTriggerRepository
from app.modules.position_monitoring.schemas import (
    MarketObservation,
    MonitorRules,
    PositionMonitorInput,
)
from app.modules.position_monitoring.service import PositionMonitoringService
from app.shared.contracts import PositionStatus
from app.shared.database import create_engine_for_database, create_session_factory
from app.shared.migrations import migrate_database


NOW = datetime(2026, 10, 31, 9, 30, tzinfo=timezone.utc)


@pytest.fixture
def monitoring_context(tmp_path: Path):
    database = tmp_path / "position-monitor.db"
    migrate_database(database, backup_dir=tmp_path / "backups")
    engine = create_engine_for_database(database)
    sessions = create_session_factory(engine)
    repository = SqlAlchemyTriggerRepository(sessions)
    service = PositionMonitoringService(triggers=repository, clock=lambda: NOW)
    yield {"engine": engine, "sessions": sessions, "repository": repository, "service": service}
    engine.dispose()


def make_position(**overrides):
    data = {
        "position_id": uuid4(),
        "symbol": "RELIANCE",
        "confirmed_open_quantity": 3,
        "average_price": Decimal("100"),
        "opened_at": NOW.replace(hour=9),
        "status": PositionStatus.OPEN,
        "market": MarketObservation(
            price=Decimal("100"), captured_at=NOW, market_open=True,
        ),
        "rules": MonitorRules(
            version="intraday-v1",
            stop_loss_price=Decimal("95"),
            target_price=Decimal("108"),
            max_market_age_seconds=30,
        ),
    }
    data.update(overrides)
    return PositionMonitorInput.model_validate(data)


def trigger_count(sessions):
    with sessions() as session:
        return session.scalar(select(func.count()).select_from(PositionTriggerRecord))
