from pathlib import Path

from app.modules.decision_engine.schemas import ApprovedOrderIntent
from app.modules.decision_engine.service import DecisionEngineService


def test_decision_boundary_is_provider_neutral_and_importable():
    assert callable(getattr(DecisionEngineService, "evaluate_entry"))
    assert "decision_id" in ApprovedOrderIntent.model_fields
    assert "quantity" in ApprovedOrderIntent.model_fields


def test_decision_engine_source_does_not_depend_on_ai_or_broker_providers():
    source_root = Path(__file__).resolve().parents[1]
    python_sources = [
        path.read_text(encoding="utf-8").lower()
        for path in source_root.rglob("*.py")
        if "tests" not in path.parts
    ]

    forbidden = ("tradingagents", "langgraph", "langchain", "dhan_gateway", "place_market_order")
    assert not [name for name in forbidden if any(name in source for source in python_sources)]
