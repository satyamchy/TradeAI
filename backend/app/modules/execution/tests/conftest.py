from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.execution.repository import SqlAlchemyExecutionRepository
from app.modules.execution.schemas import BrokerOrderUpdate
from app.modules.execution.service import ExecutionService
from app.shared.contracts import ApprovedOrderIntent, ExecutionMode, ExecutionRequest, OrderSide, OrderType
from app.shared.database import create_engine_for_database, create_session_factory
from app.shared.migrations import migrate_database


NOW = datetime(2026, 10, 31, 9, 30, tzinfo=timezone.utc)


class FakeIntentLookup:
    def __init__(self, intents):
        self.intents = {item.order_intent_id: item for item in intents}
        self.calls = 0

    async def get_approved_intent(self, intent_id, *, owner_id):
        self.calls += 1
        return self.intents.get(intent_id) if owner_id == 7 else None


class FakeBroker:
    name = "fake-paper"

    def __init__(self):
        self.submit_calls = []
        self.submit_update = BrokerOrderUpdate(
            broker="fake-paper", status="PART_TRADED", broker_order_id="fake-1",
            filled_quantity=2, average_fill_price=Decimal("100"), updated_at=NOW,
        )
        self.status_update = self.submit_update
        self.cancel_update = BrokerOrderUpdate(
            broker="fake-paper", status="CANCELLED", broker_order_id="fake-1",
            filled_quantity=2, average_fill_price=Decimal("100"), updated_at=NOW,
        )
        self.raise_submit = False

    async def submit(self, intent, *, mode):
        self.submit_calls.append((intent, mode))
        if self.raise_submit:
            raise TimeoutError("simulated response lost")
        return self.submit_update

    async def get_order_status(self, order):
        return self.status_update

    async def cancel_order(self, order):
        return self.cancel_update


@pytest.fixture
def execution_context(tmp_path: Path):
    database = tmp_path / "execution.db"
    migrate_database(database, backup_dir=tmp_path / "backups")
    engine = create_engine_for_database(database)
    sessions = create_session_factory(engine)
    intent = ApprovedOrderIntent(
        order_intent_id=uuid4(), decision_id=uuid4(), symbol="RELIANCE", security_id="2885",
        side=OrderSide.BUY, quantity=5, order_type=OrderType.MARKET,
        stop_loss=Decimal("95"), target=Decimal("108"), max_risk_amount=Decimal("25"),
        idempotency_key="decision:test-idempotency-key", expires_at=NOW.replace(minute=31),
        reference_price=Decimal("100"), exchange="NSE", segment="NSE_EQ",
        product_type="INTRADAY", intent_kind="ENTRY",
    )
    broker = FakeBroker()
    repository = SqlAlchemyExecutionRepository(sessions)
    lookup = FakeIntentLookup([intent])
    service = ExecutionService(
        intents=lookup,
        repository=repository,
        broker=broker,
        live_execution_allowed=False,
        clock=lambda: NOW,
    )
    yield {"engine": engine, "sessions": sessions, "intent": intent,
           "broker": broker, "repository": repository, "lookup": lookup, "service": service}
    engine.dispose()


def execution_request(intent, mode=ExecutionMode.PAPER):
    return ExecutionRequest(order_intent_id=intent.order_intent_id, execution_mode=mode)
