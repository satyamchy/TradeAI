import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.modules.execution.models import ExecutionEventRecord, ExecutionOrderRecord
from app.modules.execution.service import (
    ExecutionService,
    IntentUnavailable,
    InvalidExecutionRequest,
    LiveExecutionDisabled,
)
from app.shared.contracts import ExecutionMode, OrderStatus

from .conftest import NOW, execution_request


def test_partial_fill_reconcile_and_repeat_are_idempotent(execution_context):
    ctx = execution_context
    request = execution_request(ctx["intent"])
    first = asyncio.run(ctx["service"].execute_order(request, owner_id=7))
    duplicate = asyncio.run(ctx["service"].execute_order(request, owner_id=7))

    assert first.status is OrderStatus.PARTIALLY_FILLED
    assert first.filled_quantity == 2
    assert first.remaining_quantity == 3
    assert duplicate == first
    assert len(ctx["broker"].submit_calls) == 1

    ctx["broker"].status_update = ctx["broker"].status_update.model_copy(update={
        "status": "TRADED", "filled_quantity": 5, "average_fill_price": Decimal("100.25")
    })
    reconciled = asyncio.run(ctx["service"].reconcile_order(first.tradeai_order_id, owner_id=7))
    assert reconciled.status is OrderStatus.FILLED
    assert reconciled.filled_quantity == 5
    assert reconciled.remaining_quantity == 0
    assert reconciled.average_fill_price == Decimal("100.25")
    with ctx["sessions"]() as session:
        assert session.scalar(select(func.count()).select_from(ExecutionOrderRecord)) == 1
        assert session.scalar(select(func.count()).select_from(ExecutionEventRecord)) == 3


def test_timeout_is_unknown_and_never_blindly_retried(execution_context):
    ctx = execution_context
    ctx["broker"].raise_submit = True
    request = execution_request(ctx["intent"])
    first = asyncio.run(ctx["service"].execute_order(request, owner_id=7))
    duplicate = asyncio.run(ctx["service"].execute_order(request, owner_id=7))

    assert first.status is OrderStatus.UNKNOWN
    assert first.rejection_reason == "SUBMISSION_OUTCOME_UNKNOWN"
    assert duplicate == first
    assert len(ctx["broker"].submit_calls) == 1

    ctx["broker"].status_update = ctx["broker"].status_update.model_copy(update={
        "status": "OPEN", "filled_quantity": 1
    })
    recovered = asyncio.run(ctx["service"].reconcile_order(first.tradeai_order_id, owner_id=7))
    assert recovered.status is OrderStatus.PARTIALLY_FILLED
    assert recovered.filled_quantity == 1
    assert recovered.remaining_quantity == 4


def test_rejected_order_and_reconciliation_batch(execution_context):
    ctx = execution_context
    ctx["broker"].submit_update = ctx["broker"].submit_update.model_copy(update={
        "status": "REJECTED", "filled_quantity": 0,
        "rejection_reason": "credential access_token=super-secret rejected",
    })
    result = asyncio.run(ctx["service"].execute_order(execution_request(ctx["intent"]), owner_id=7))
    assert result.status is OrderStatus.REJECTED
    assert "super-secret" not in (result.rejection_reason or "")

    summary = asyncio.run(ctx["service"].reconcile_orders(owner_id=7))
    assert summary.checked == 0  # terminal rejects need no broker poll


def test_cancel_preserves_confirmed_partial_fill(execution_context):
    ctx = execution_context
    submitted = asyncio.run(ctx["service"].execute_order(execution_request(ctx["intent"]), owner_id=7))
    assert submitted.status is OrderStatus.PARTIALLY_FILLED
    cancelled = asyncio.run(ctx["service"].cancel_order(submitted.tradeai_order_id, owner_id=7))
    assert cancelled.status is OrderStatus.CANCELLED
    assert cancelled.filled_quantity == 2
    assert cancelled.remaining_quantity == 3


def test_live_mode_is_disabled_and_unapproved_intents_are_not_executable(execution_context):
    ctx = execution_context
    with pytest.raises(LiveExecutionDisabled):
        asyncio.run(ctx["service"].execute_order(
            execution_request(ctx["intent"], ExecutionMode.LIVE), owner_id=7
        ))
    with pytest.raises(IntentUnavailable):
        asyncio.run(ctx["service"].execute_order(
            execution_request(ctx["intent"].model_copy(update={"order_intent_id": uuid4()})), owner_id=7
        ))
    assert ctx["broker"].submit_calls == []


def test_expired_or_unsupported_intents_fail_before_broker(execution_context):
    ctx = execution_context
    expired = ctx["intent"].model_copy(update={"expires_at": NOW - timedelta(seconds=1)})
    ctx["lookup"].intents[expired.order_intent_id] = expired
    with pytest.raises(InvalidExecutionRequest, match="expired"):
        asyncio.run(ctx["service"].execute_order(execution_request(expired), owner_id=7))

    limit = ctx["intent"].model_copy(update={"order_intent_id": uuid4(), "order_type": "LIMIT"})
    ctx["lookup"].intents[limit.order_intent_id] = limit
    with pytest.raises(InvalidExecutionRequest, match="market orders only"):
        asyncio.run(ctx["service"].execute_order(execution_request(limit), owner_id=7))
    assert ctx["broker"].submit_calls == []


def test_importing_execution_does_not_initialize_a_broker_client():
    from pathlib import Path

    module_dir = Path(__file__).resolve().parents[1]
    forbidden = ("dhanhq", "from app.broker.dhan_gateway", "TradingGateway(", "PaperLedger(")
    for source in module_dir.glob("*.py"):
        text = source.read_text(encoding="utf-8").lower()
        assert not [item for item in forbidden if item.lower() in text], source.name
