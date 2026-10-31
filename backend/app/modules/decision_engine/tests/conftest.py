from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.decision_engine.repository import SqlAlchemyDecisionRepository
from app.modules.decision_engine.schemas import (
    AccountRiskSnapshot,
    MarketSnapshot,
    StrategyPolicy,
)
from app.modules.decision_engine.service import DecisionEngineService
from app.shared.contracts import (
    AnalysisDirection,
    AnalysisHorizon,
    AnalysisResult,
    AnalysisStatus,
    Candidate,
    CandidateValidationStatus,
    Instrument,
    ProviderName,
    SelectionMode,
)
from app.shared.database import create_engine_for_database, create_session_factory
from app.shared.migrations import migrate_database


NOW = datetime(2026, 10, 31, 9, 30, tzinfo=timezone.utc)


class FakeAnalysisLookup:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def get_analysis(self, analysis_id, *, owner_id):
        self.calls += 1
        return self.result if owner_id == 7 and analysis_id == self.result.analysis_id else None


class FakeCandidateLookup:
    def __init__(self, candidate):
        self.candidate = candidate

    async def get_candidate(self, candidate_id, *, owner_id):
        return self.candidate if owner_id == 7 and candidate_id == self.candidate.candidate_id else None


class FakeMarketProvider:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    async def get_snapshot(self, symbol):
        return self.snapshot


class FakeAccountProvider:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    async def get_snapshot(self, *, owner_id):
        return self.snapshot if owner_id == 7 else None


@pytest.fixture
def decision_context(tmp_path: Path):
    db_path = tmp_path / "decision-engine.db"
    migrate_database(db_path, backup_dir=tmp_path / "backups")
    engine = create_engine_for_database(db_path)
    sessions = create_session_factory(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO users "
            "(id, username, password_hash, role, disabled, automation_state, automation_methods, created_at) "
            "VALUES (7, 'decision-test', 'unused', 'trader', 0, 'off', '[]', :created)"
        ), {"created": NOW.isoformat()})

    candidate = Candidate(
        candidate_id=uuid4(),
        batch_id=uuid4(),
        instrument=Instrument(
            symbol="RELIANCE", exchange="NSE", trading_symbol="RELIANCE",
            analysis_ticker="RELIANCE.NS", security_id="2885", segment="NSE_EQ",
        ),
        selection_mode=SelectionMode.MANUAL,
        selection_reason="USER_SELECTED",
        validation_status=CandidateValidationStatus.VALID,
        mapping_source="TEST",
        resolved_at=NOW,
        created_at=NOW,
    )
    analysis = AnalysisResult(
        analysis_id=uuid4(), candidate_id=candidate.candidate_id,
        symbol="RELIANCE", analysis_ticker="RELIANCE.NS",
        provider=ProviderName.TRADING_AGENTS, provider_version="test",
        profile_key="TEST", profile_version="1", analysis_date=NOW.date(),
        horizon=AnalysisHorizon.INTRADAY, status=AnalysisStatus.COMPLETED,
        source_rating="Buy", direction=AnalysisDirection.BULLISH,
        completed_at=NOW,
    )
    market = MarketSnapshot(symbol="RELIANCE", price=Decimal("100"), captured_at=NOW, market_open=True)
    account = AccountRiskSnapshot(
        captured_at=NOW,
        available_funds=Decimal("10000"),
        total_exposure=Decimal("0"),
        daily_loss=Decimal("0"),
    )
    policy = StrategyPolicy(
        key="intraday-test", version="1", max_risk_amount=Decimal("100"),
        risk_budget_fraction=Decimal("0.1"), max_order_value=Decimal("3000"),
        max_symbol_exposure=Decimal("5000"), max_total_exposure=Decimal("8000"),
        max_daily_loss=Decimal("1000"), stop_loss_pct=Decimal("5"), target_pct=Decimal("8"),
    )
    repository = SqlAlchemyDecisionRepository(sessions)
    yield {
        "engine": engine,
        "sessions": sessions,
        "candidate": candidate,
        "analysis": analysis,
        "market": market,
        "account": account,
        "policy": policy,
        "repository": repository,
    }
    engine.dispose()


@pytest.fixture
def make_service(decision_context):
    def factory(*, analysis=None, candidate=None, market=None, market_provider=None, account=None, policy=None):
        selected_policy = policy or decision_context["policy"]
        return DecisionEngineService(
            analyses=FakeAnalysisLookup(analysis or decision_context["analysis"]),
            candidates=FakeCandidateLookup(candidate or decision_context["candidate"]),
            market=market_provider or FakeMarketProvider(market or decision_context["market"]),
            accounts=FakeAccountProvider(account or decision_context["account"]),
            repository=decision_context["repository"],
            strategies={selected_policy.key: selected_policy},
            clock=lambda: NOW,
        )

    return factory
