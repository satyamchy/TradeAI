import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.modules.decision_engine.models import DecisionRecord, OrderIntentRecord
from app.modules.decision_engine.schemas import (
    ConfirmedPosition,
    EvaluateTradeRequest,
    ExitEvaluationRequest,
)
from app.modules.decision_engine.service import DecisionInputsUnavailable
from app.shared.contracts import AnalysisDirection, DecisionStatus

from .conftest import NOW
from .conftest import FakeMarketProvider


def request(context):
    return EvaluateTradeRequest(
        analysis_id=context["analysis"].analysis_id,
        strategy_key=context["policy"].key,
        requested_action="ENTRY",
    )


def test_bullish_entry_generates_deterministic_sized_persisted_intent(decision_context, make_service):
    service = make_service()
    result = asyncio.run(service.evaluate_entry(request(decision_context), owner_id=7))
    repeated = asyncio.run(service.evaluate_entry(request(decision_context), owner_id=7))

    assert result.status is DecisionStatus.BUY_APPROVED
    assert result.order_intent is not None
    assert result.order_intent.quantity == 20  # INR 100 risk / INR 5 risk per share
    assert result.order_intent.stop_loss == Decimal("95.00")
    assert result.order_intent.target == Decimal("108.00")
    assert result.order_intent.max_risk_amount == Decimal("100.00")
    assert result.decision_id == result.order_intent.decision_id == repeated.decision_id
    assert result.order_intent.idempotency_key == repeated.order_intent.idempotency_key
    assert asyncio.run(service.get_approved_intent(result.order_intent.order_intent_id, owner_id=7)) == result.order_intent
    assert asyncio.run(service.get_approved_intent(result.order_intent.order_intent_id, owner_id=8)) is None
    with decision_context["sessions"]() as session:
        assert session.scalar(select(func.count()).select_from(DecisionRecord)) == 1
        assert session.scalar(select(func.count()).select_from(OrderIntentRecord)) == 1


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("kill_switch_enabled", True, "KILL_SWITCH_ENABLED"),
        ("daily_loss", Decimal("1000"), "DAILY_LOSS_LIMIT_REACHED"),
        ("available_funds", Decimal("0"), "NO_AVAILABLE_FUNDS"),
    ],
)
def test_risk_guards_fail_closed_without_intent(decision_context, make_service, field, value, expected):
    snapshot = decision_context["account"].model_copy(update={field: value})
    result = asyncio.run(make_service(account=snapshot).evaluate_entry(request(decision_context), owner_id=7))
    assert result.status is DecisionStatus.REJECTED
    assert expected in result.reason_codes
    assert result.order_intent is None


def test_market_and_analysis_staleness_fail_closed(decision_context, make_service):
    stale_market = decision_context["market"].model_copy(update={"captured_at": NOW - timedelta(minutes=1)})
    result = asyncio.run(make_service(market=stale_market).evaluate_entry(request(decision_context), owner_id=7))
    assert result.status is DecisionStatus.REJECTED
    assert "MARKET_DATA_STALE" in result.reason_codes
    assert result.order_intent is None

    stale_analysis = decision_context["analysis"].model_copy(update={"completed_at": NOW - timedelta(hours=2)})
    result = asyncio.run(make_service(analysis=stale_analysis).evaluate_entry(request(decision_context), owner_id=7))
    assert "ANALYSIS_STALE" in result.reason_codes
    assert result.order_intent is None


@pytest.mark.parametrize(
    ("direction", "expected"),
    [
        (AnalysisDirection.NEUTRAL, DecisionStatus.HOLD),
        (AnalysisDirection.BEARISH, DecisionStatus.REJECTED),
        (AnalysisDirection.REVIEW, DecisionStatus.REVIEW_REQUIRED),
    ],
)
def test_non_bullish_analysis_never_creates_entry_intent(decision_context, make_service, direction, expected):
    analysis = decision_context["analysis"].model_copy(update={"direction": direction})
    result = asyncio.run(make_service(analysis=analysis).evaluate_entry(request(decision_context), owner_id=7))
    assert result.status is expected
    assert result.order_intent is None


def test_position_pending_order_exposure_limit_and_missing_security_reject(decision_context, make_service):
    existing = ConfirmedPosition(
        symbol="RELIANCE", security_id="2885", quantity=1,
        average_price=Decimal("100"), market_value=Decimal("100"),
    )
    duplicate = decision_context["account"].model_copy(update={"confirmed_positions": [existing]})
    result = asyncio.run(make_service(account=duplicate).evaluate_entry(request(decision_context), owner_id=7))
    assert "DUPLICATE_POSITION" in result.reason_codes
    assert result.order_intent is None

    pending = decision_context["account"].model_copy(update={"pending_symbols": ["RELIANCE"]})
    result = asyncio.run(make_service(account=pending).evaluate_entry(request(decision_context), owner_id=7))
    assert "PENDING_ORDER_EXISTS" in result.reason_codes

    no_security = decision_context["candidate"].model_copy(update={
        "instrument": decision_context["candidate"].instrument.model_copy(update={"security_id": None})
    })
    result = asyncio.run(make_service(candidate=no_security).evaluate_entry(request(decision_context), owner_id=7))
    assert "SECURITY_ID_UNRESOLVED" in result.reason_codes
    assert result.order_intent is None


def test_market_closed_position_capacity_and_exposure_caps_fail_closed(decision_context, make_service):
    closed_market = decision_context["market"].model_copy(update={"market_open": False})
    result = asyncio.run(make_service(market=closed_market).evaluate_entry(request(decision_context), owner_id=7))
    assert "MARKET_CLOSED" in result.reason_codes
    assert result.order_intent is None

    positions = [
        ConfirmedPosition(
            symbol=f"OTHER{index}", security_id=str(index + 1), quantity=1,
            average_price=Decimal("100"), market_value=Decimal("100"),
        )
        for index in range(4)
    ]
    full_portfolio = decision_context["account"].model_copy(update={"confirmed_positions": positions})
    result = asyncio.run(make_service(account=full_portfolio).evaluate_entry(request(decision_context), owner_id=7))
    assert "MAX_POSITIONS_REACHED" in result.reason_codes

    near_cap = decision_context["account"].model_copy(update={"total_exposure": Decimal("8000")})
    result = asyncio.run(make_service(account=near_cap).evaluate_entry(request(decision_context), owner_id=7))
    assert result.status is DecisionStatus.REJECTED
    assert "EXPOSURE_LIMIT_REACHED" in result.reason_codes
    assert result.order_intent is None


def test_position_size_obeys_available_funds_and_order_value(decision_context, make_service):
    low_cash = decision_context["account"].model_copy(update={"available_funds": Decimal("500")})
    result = asyncio.run(make_service(account=low_cash).evaluate_entry(request(decision_context), owner_id=7))
    assert result.order_intent is not None and result.order_intent.quantity == 5

    narrow_order = decision_context["policy"].model_copy(update={"max_order_value": Decimal("600")})
    result = asyncio.run(make_service(policy=narrow_order).evaluate_entry(request(decision_context), owner_id=7))
    assert result.order_intent is not None and result.order_intent.quantity == 6


def test_missing_market_and_invalid_stop_loss_fail_closed(decision_context, make_service):
    unavailable = make_service(market_provider=FakeMarketProvider(None))
    with pytest.raises(DecisionInputsUnavailable, match="Fresh market and account"):
        asyncio.run(unavailable.evaluate_entry(request(decision_context), owner_id=7))

    tiny_price = decision_context["market"].model_copy(update={"price": Decimal("0.01")})
    severe_stop = decision_context["policy"].model_copy(update={"stop_loss_pct": Decimal("99")})
    result = asyncio.run(make_service(market=tiny_price, policy=severe_stop).evaluate_entry(
        request(decision_context), owner_id=7
    ))
    assert result.status is DecisionStatus.REJECTED
    assert "INVALID_STOP_LOSS" in result.reason_codes
    assert result.order_intent is None

def test_exit_is_ai_independent_and_bounded_by_account_confirmed_quantity(decision_context, make_service):
    quantity = ConfirmedPosition(
        symbol="RELIANCE", security_id="2885", quantity=4,
        average_price=Decimal("90"), market_value=Decimal("400"),
    )
    account = decision_context["account"].model_copy(update={"confirmed_positions": [quantity]})
    service = make_service(account=account)
    exit_request = ExitEvaluationRequest(
        position_id=uuid4(), symbol="RELIANCE", security_id="2885",
        confirmed_open_quantity=4, requested_quantity=3,
        average_price=Decimal("90"), strategy_key=decision_context["policy"].key,
        strategy_version=decision_context["policy"].version, reason="STOP_LOSS",
    )
    result = asyncio.run(service.evaluate_exit(exit_request, owner_id=7))
    assert result.status is DecisionStatus.SELL_APPROVED
    assert result.analysis_id is None
    assert result.order_intent is not None
    assert result.order_intent.side.value == "SELL"
    assert result.order_intent.quantity == 3
    assert result.order_intent.intent_kind == "EXIT"
    assert "AI_NOT_REQUIRED_FOR_EXIT" in result.reason_codes

    too_many = exit_request.model_copy(update={"requested_quantity": 5})
    rejected = asyncio.run(service.evaluate_exit(too_many, owner_id=7))
    assert rejected.status is DecisionStatus.REJECTED
    assert rejected.order_intent is None
    assert "EXIT_QUANTITY_EXCEEDS_CONFIRMED_QUANTITY" in rejected.reason_codes


def test_missing_analysis_input_is_reported(decision_context, make_service):
    missing = decision_context["analysis"].model_copy(update={"analysis_id": uuid4()})
    service = make_service(analysis=missing)
    request_with_missing = request(decision_context).model_copy(update={"analysis_id": uuid4()})
    with pytest.raises(DecisionInputsUnavailable):
        asyncio.run(service.evaluate_entry(request_with_missing, owner_id=7))


def test_decision_module_has_no_ai_provider_or_broker_order_imports():
    from pathlib import Path

    module_dir = Path(__file__).resolve().parents[1]
    forbidden = ("tradingagents", "langchain", "langgraph", "dhan_gateway", "TradingGateway", "place_market_order")
    for source in module_dir.glob("*.py"):
        text = source.read_text(encoding="utf-8").lower()
        assert not [name for name in forbidden if name.lower() in text], source.name
