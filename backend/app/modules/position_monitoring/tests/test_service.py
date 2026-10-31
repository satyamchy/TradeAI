from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from app.modules.position_monitoring.schemas import MarketObservation, MonitorRules
from app.shared.contracts import PositionStatus

from .conftest import NOW, make_position, trigger_count


def test_stop_and_target_trigger_at_exact_boundaries(monitoring_context):
    service = monitoring_context["service"]
    stop = service.evaluate(make_position(market=MarketObservation(
        price=Decimal("95"), captured_at=NOW, market_open=True,
    )))
    target = service.evaluate(make_position(market=MarketObservation(
        price=Decimal("108"), captured_at=NOW, market_open=True,
    )))

    assert stop.action == target.action == "EXIT_CANDIDATE"
    assert stop.trigger_reason == "STOP_LOSS"
    assert target.trigger_reason == "TARGET_REACHED"
    assert stop.exit_quantity == target.exit_quantity == 3
    assert stop.unrealized_pnl == Decimal("-15")
    assert target.unrealized_pnl == Decimal("24")
    assert stop.is_new_trigger is target.is_new_trigger is True


def test_unchanged_trigger_is_deduplicated_for_partial_confirmed_quantity(monitoring_context):
    ctx = monitoring_context
    position_id = make_position().position_id
    position = make_position(
        position_id=position_id,
        confirmed_open_quantity=2,
        market=MarketObservation(price=Decimal("94"), captured_at=NOW, market_open=True),
    )
    first = ctx["service"].evaluate(position)
    second = ctx["service"].evaluate(position.model_copy(update={
        "market": MarketObservation(price=Decimal("93"), captured_at=NOW, market_open=True)
    }))

    assert first.trigger_id == second.trigger_id
    assert first.is_new_trigger is True
    assert second.is_new_trigger is False
    assert first.exit_quantity == second.exit_quantity == 2
    assert trigger_count(ctx["sessions"]) == 1


def test_square_off_is_deterministic_even_without_fresh_market_data(monitoring_context):
    rules = MonitorRules(version="squareoff-v1", square_off_at=NOW)
    position = make_position(
        market=MarketObservation(price=None, captured_at=None, market_open=False),
        rules=rules,
    )
    result = monitoring_context["service"].evaluate(position)
    assert result.action == "EXIT_CANDIDATE"
    assert result.trigger_reason == "SESSION_SQUARE_OFF"
    assert result.exit_quantity == position.confirmed_open_quantity
    assert result.current_price is None
    assert result.unrealized_pnl is None


def test_stale_missing_and_closed_market_are_data_unavailable(monitoring_context):
    stale = make_position(market=MarketObservation(
        price=Decimal("90"), captured_at=NOW - timedelta(minutes=1), market_open=True,
    ))
    missing = make_position(market=MarketObservation(price=None, captured_at=None, market_open=True))
    closed = make_position(market=MarketObservation(price=Decimal("90"), captured_at=NOW, market_open=False))

    for position, reason in [(stale, "MARKET_DATA_STALE"), (missing, "MARKET_DATA_MISSING"), (closed, "MARKET_CLOSED")]:
        result = monitoring_context["service"].evaluate(position)
        assert result.action == "DATA_UNAVAILABLE"
        assert result.status is PositionStatus.DATA_UNAVAILABLE
        assert result.trigger_reason == reason
        assert result.exit_quantity is None
    assert trigger_count(monitoring_context["sessions"]) == 0


def test_no_price_rule_match_holds_and_partial_exit_quantity_is_not_invented(monitoring_context):
    position = make_position(
        confirmed_open_quantity=1,
        market=MarketObservation(price=Decimal("100"), captured_at=NOW, market_open=True),
    )
    result = monitoring_context["service"].evaluate(position)
    assert result.action == "HOLD"
    assert result.status is PositionStatus.OPEN
    assert result.exit_quantity is None
    assert result.unrealized_pnl == Decimal("0")
    assert trigger_count(monitoring_context["sessions"]) == 0


def test_monitoring_has_no_ai_or_execution_dependencies():
    module_dir = Path(__file__).resolve().parents[1]
    forbidden = ("tradingagents", "langchain", "langgraph", "dhan", "app.modules.execution", "place_order")
    for source in module_dir.glob("*.py"):
        text = source.read_text(encoding="utf-8").lower()
        assert not [name for name in forbidden if name.lower() in text], source.name
