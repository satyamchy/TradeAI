import asyncio
import copy
import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.ai_analysis.providers import TradingAgentsProvider, normalize_direction
from app.modules.ai_analysis.schemas import (
    AnalysisProfile,
    AnalysisProviderRequest,
    PortfolioPosition,
    PortfolioSnapshotReference,
)
from app.shared.contracts import AnalysisHorizon, Instrument


def provider_request(tmp_path, *, save_html=True, portfolio=True):
    profile = AnalysisProfile(
        key="TEST_RESEARCH",
        version="1",
        horizon=AnalysisHorizon.INTRADAY,
        selected_analysts=("market", "news"),
        quick_provider="groq",
        quick_model="quick-model",
        deep_provider="openai",
        deep_model="deep-model",
        max_debate_rounds=2,
        max_risk_discuss_rounds=1,
        checkpoint_enabled=False,
        save_html_report=save_html,
    )
    snapshot = (
        PortfolioSnapshotReference(
            snapshot_id=uuid4(),
            captured_at=datetime.now(timezone.utc),
            currency="INR",
            cash=Decimal("10000"),
            positions=[],
        )
        if portfolio
        else None
    )
    return AnalysisProviderRequest(
        analysis_id=uuid4(),
        candidate_id=uuid4(),
        instrument=Instrument(
            symbol="RELIANCE",
            exchange="NSE",
            trading_symbol="RELIANCE",
            analysis_ticker="RELIANCE.NS",
            security_id=None,
            segment="NSE_EQ",
        ),
        analysis_date=date(2026, 10, 30),
        horizon=AnalysisHorizon.INTRADAY,
        profile=profile,
        portfolio=snapshot,
    )


def test_adapter_copies_config_runs_blocking_graph_and_saves_isolated_artifact(tmp_path):
    defaults = {
        "llm_provider": "openai",
        "quick_think_llm": "old-quick",
        "deep_think_llm": "old-deep",
        "quick_think_provider": None,
        "deep_think_provider": None,
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "checkpoint_enabled": False,
        "data_cache_dir": "old-cache",
        "memory_log_path": "old-memory",
        "results_dir": "old-results",
        "api_key": "never-persist",
    }
    untouched = copy.deepcopy(defaults)
    captured = {}

    class FakeGraph:
        def __init__(self, *, selected_analysts, debug, config):
            captured["analysts"] = selected_analysts
            captured["debug"] = debug
            captured["config"] = config

        def propagate(self, ticker, analysis_date, *, asset_type, portfolio):
            captured["call"] = (ticker, analysis_date, asset_type, portfolio)
            return {
                "market_report": "Market report",
                "news_report": "News report",
                "investment_plan": "Bull and bear plan",
                "trader_investment_plan": "Trader plan",
                "risk_debate_state": {"aggressive_history": ["risk note"]},
                "final_trade_decision": "Rating: Overweight",
            }, "Overweight"

        def save_reports(self, state, ticker, *, save_path, html):
            path = Path(save_path) / "complete_report.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("<html>safe report</html>", encoding="utf-8")
            captured["saved"] = (ticker, html, Path(save_path))

    provider = TradingAgentsProvider(
        data_root=tmp_path / "data",
        environment="development-paper",
        graph_factory=FakeGraph,
        default_config=defaults,
        provider_version="0.7.1",
        portfolio_factory=lambda value: value,
    )
    result = asyncio.run(provider.analyze(provider_request(tmp_path)))

    config = captured["config"]
    assert defaults == untouched
    assert captured["analysts"] == ["market", "news"]
    assert captured["debug"] is False
    assert captured["call"][0:3] == ("RELIANCE.NS", "2026-10-30", "stock")
    assert captured["call"][3]["positions"] == []
    assert captured["call"][3]["cash"] == 10000.0
    assert config["quick_think_provider"] == "groq"
    assert config["quick_think_llm"] == "quick-model"
    assert config["deep_think_provider"] == "openai"
    assert config["deep_think_llm"] == "deep-model"
    assert config["max_debate_rounds"] == 2
    assert config["checkpoint_enabled"] is False
    assert "development-paper" in config["memory_log_path"]
    assert config["api_key"] == "never-persist"  # needed only by the graph; never stored or logged by TradeX
    assert "never-persist" not in repr(result)
    assert result.provider_version == "0.7.1"
    assert result.source_rating == "Overweight"
    assert result.reports["bull_bear_research"] == "Bull and bear plan"
    assert result.reports["risk_assessment"] == "risk note"
    relative_path = result.report_artifacts["html_report_path"]
    artifact = tmp_path / "data" / relative_path
    assert artifact.read_text(encoding="utf-8") == "<html>safe report</html>"
    assert result.report_artifacts["report_checksum"] == "sha256:" + hashlib.sha256(
        artifact.read_bytes()
    ).hexdigest()


def test_adapter_does_not_save_reports_when_disabled(tmp_path):
    class FakeGraph:
        def __init__(self, **kwargs):
            pass

        def propagate(self, *args, **kwargs):
            return {"market_report": "market"}, "Hold"

        def save_reports(self, *args, **kwargs):
            raise AssertionError("reports are disabled")

    defaults = {
        "llm_provider": "openai", "quick_think_llm": "q", "deep_think_llm": "d",
        "quick_think_provider": None, "deep_think_provider": None, "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1, "checkpoint_enabled": False, "data_cache_dir": "c",
        "memory_log_path": "m", "results_dir": "r",
    }
    provider = TradingAgentsProvider(
        data_root=tmp_path,
        environment="test-paper",
        graph_factory=FakeGraph,
        default_config=defaults,
        provider_version="0.7.1",
        portfolio_factory=lambda value: value,
    )

    result = asyncio.run(provider.analyze(provider_request(tmp_path, save_html=False, portfolio=False)))

    assert result.report_artifacts == {}


@pytest.mark.parametrize(
    ("rating", "direction"),
    [
        ("Buy", "BULLISH"),
        ("Overweight", "BULLISH"),
        ("Hold", "NEUTRAL"),
        ("Underweight", "BEARISH"),
        ("Sell", "BEARISH"),
        ("REVIEW", "REVIEW"),
        ("not a rating", "REVIEW"),
        (None, "REVIEW"),
    ],
)
def test_rating_normalization_preserves_five_tier_direction(rating, direction):
    assert normalize_direction(rating) == direction
