from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.jobs.repository import SqlAlchemyAnalysisJobRepository
from app.jobs.service import AnalysisJobManager
from app.modules.ai_analysis.profiles import default_profile_registry
from app.modules.ai_analysis.repository import SqlAlchemyAnalysisRunRepository
from app.modules.ai_analysis.schemas import AnalysisProviderOutput
from app.modules.ai_analysis.service import AIAnalysisService
from app.modules.decision_engine.repository import SqlAlchemyDecisionRepository
from app.modules.decision_engine.schemas import (
    AccountRiskSnapshot,
    ConfirmedPosition,
    MarketSnapshot,
    StrategyPolicy,
)
from app.modules.decision_engine.service import DecisionEngineService
from app.modules.execution.repository import SqlAlchemyExecutionRepository
from app.modules.execution.schemas import BrokerOrderUpdate
from app.modules.execution.service import ExecutionService, LiveExecutionDisabled
from app.modules.position_monitoring.repository import SqlAlchemyTriggerRepository
from app.modules.position_monitoring.schemas import MarketObservation, MonitorRules
from app.modules.position_monitoring.service import PositionMonitoringService
from app.modules.stock_selection.instrument_master import InstrumentResolution
from app.modules.stock_selection.repository import SqlAlchemyCandidateRepository
from app.modules.stock_selection.service import CandidateNotFoundError, StockSelectionService
from app.shared.contracts import (
    AnalysisHorizon,
    AnalysisDirection,
    AnalysisRequest,
    AnalysisStatus,
    CreateCandidatesRequest,
    DecisionStatus,
    ExecutionMode,
    OrderStatus,
    ProviderName,
    SelectionMode,
)
from app.shared.database import create_engine_for_database, create_session_factory
from app.shared.migrations import migrate_database
from app.workflows.analysis import CandidateNotReadyForAnalysis, StockSelectionAnalysisWorkflow
from app.workflows.decision import AnalysisDecisionWorkflow, AnalysisUnavailable
from app.workflows.execution import DecisionExecutionWorkflow, DecisionNotExecutable
from app.workflows.monitoring import ExecutionPositionWorkflow, PositionNotReadyForMonitoring
from app.workflows.exits import PositionExitWorkflow
from app.workflows.schemas import ConfirmedOpenPosition


NOW = datetime(2026, 10, 31, 9, 30, tzinfo=timezone.utc)


class FakeInstrumentResolver:
    def resolve(self, symbol: str, exchange: str) -> InstrumentResolution:
        from app.shared.contracts import Instrument

        return InstrumentResolution(
            instrument=Instrument(
                symbol=symbol,
                exchange=exchange,
                trading_symbol=symbol,
                analysis_ticker=f"{symbol}.NS",
                security_id="2885",
                segment="NSE_EQ",
            ),
            mapping_source="TEST_MASTER",
            resolved_at=NOW,
        )


class FakeAnalysisProvider:
    version = "integration-test"

    def __init__(self):
        self.requests = []

    async def analyze(self, request):
        self.requests.append(request)
        return AnalysisProviderOutput(
            provider_version=self.version,
            source_rating=getattr(self, "source_rating", "Overweight"),
            reports={"portfolio_decision": "Rating: Overweight"},
        )


class FakeMarketProvider:
    async def get_snapshot(self, symbol):
        return MarketSnapshot(
            symbol=symbol, price=Decimal("100"), captured_at=datetime.now(timezone.utc), market_open=True
        )


class FakeAccountProvider:
    def __init__(self):
        self.positions = []

    async def get_snapshot(self, *, owner_id):
        if owner_id != 1:
            return None
        return AccountRiskSnapshot(
            captured_at=datetime.now(timezone.utc),
            available_funds=Decimal("10000"),
            total_exposure=Decimal("0"),
            daily_loss=Decimal("0"),
            confirmed_positions=list(self.positions),
        )


class FakeOpenPositionProvider:
    def __init__(self):
        self.positions = {}
        self.calls = []

    async def get_open_position(self, *, owner_id, symbol, security_id, product_type):
        key = (owner_id, symbol, security_id, product_type)
        self.calls.append(key)
        return self.positions.get(key)


class FakeBroker:
    name = "integration-paper"

    def __init__(self):
        self.submit_calls = []
        self.raise_submit = False
        self.reconciled_quantity = None
        self.submit_update = BrokerOrderUpdate(
            broker=self.name,
            status="PART_TRADED",
            broker_order_id="paper-42",
            filled_quantity=2,
            average_fill_price=Decimal("100"),
            updated_at=datetime.now(timezone.utc),
        )

    async def submit(self, intent, *, mode):
        self.submit_calls.append((intent, mode))
        if self.raise_submit:
            raise TimeoutError("paper response lost after acceptance")
        return self.submit_update

    async def get_order_status(self, order):
        quantity = (
            order.requested_quantity
            if self.reconciled_quantity is None
            else self.reconciled_quantity
        )
        status = "FILLED" if quantity == order.requested_quantity else (
            "PART_TRADED" if quantity > 0 else "OPEN"
        )
        return self.submit_update.model_copy(
            update={
                "status": status,
                "filled_quantity": quantity,
                "average_fill_price": Decimal("100") if quantity else None,
            }
        )

    async def cancel_order(self, order):
        return self.status_update.model_copy(update={"status": "CANCELLED"})


@pytest.fixture
def i1_workflow(tmp_path: Path):
    database = tmp_path / "workflow-i1.sqlite"
    migrate_database(database, backup_dir=tmp_path / "backups")
    engine = create_engine_for_database(database)
    sessions = create_session_factory(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO users (username, password_hash, role, disabled, automation_state, "
            "automation_methods, created_at) VALUES ('i1-test', 'unused', 'trader', 0, 'off', '[]', :now)"
        ), {"now": NOW.isoformat()})

    candidate_service = StockSelectionService(
        SqlAlchemyCandidateRepository(sessions), FakeInstrumentResolver()
    )
    jobs = AnalysisJobManager(SqlAlchemyAnalysisJobRepository(sessions))
    provider = FakeAnalysisProvider()
    analysis_service = AIAnalysisService(
        jobs=jobs,
        repository=SqlAlchemyAnalysisRunRepository(sessions),
        candidates=candidate_service,
        profiles=default_profile_registry(),
        provider=provider,
    )
    policy = StrategyPolicy(
        key="intraday-test", version="1", max_analysis_age_seconds=3600,
        max_risk_amount=Decimal("100"), risk_budget_fraction=Decimal("0.1"),
        max_order_value=Decimal("3000"), max_symbol_exposure=Decimal("5000"),
        max_total_exposure=Decimal("8000"), max_daily_loss=Decimal("1000"),
        stop_loss_pct=Decimal("5"), target_pct=Decimal("8"),
    )
    account_provider = FakeAccountProvider()
    decision_service = DecisionEngineService(
        analyses=analysis_service,
        candidates=candidate_service,
        market=FakeMarketProvider(),
        accounts=account_provider,
        repository=SqlAlchemyDecisionRepository(sessions),
        strategies={policy.key: policy},
    )
    broker = FakeBroker()
    execution_service = ExecutionService(
        intents=decision_service,
        repository=SqlAlchemyExecutionRepository(sessions),
        broker=broker,
        live_execution_allowed=False,
    )
    workflow = StockSelectionAnalysisWorkflow(candidate_service, analysis_service)
    decision_workflow = AnalysisDecisionWorkflow(analysis_service, decision_service)
    execution_workflow = DecisionExecutionWorkflow(decision_service, execution_service)
    monitoring_service = PositionMonitoringService(
        triggers=SqlAlchemyTriggerRepository(sessions),
    )
    position_provider = FakeOpenPositionProvider()
    position_workflow = ExecutionPositionWorkflow(
        execution_service, decision_service, monitoring_service, position_provider
    )
    exit_workflow = PositionExitWorkflow(decision_service, execution_workflow)
    yield {"engine": engine, "sessions": sessions, "workflow": workflow,
           "candidate_service": candidate_service, "analysis_service": analysis_service,
           "provider": provider, "decision_service": decision_service,
           "decision_workflow": decision_workflow, "policy": policy,
           "execution_service": execution_service, "execution_workflow": execution_workflow,
           "broker": broker, "monitoring_service": monitoring_service,
           "position_workflow": position_workflow, "exit_workflow": exit_workflow,
           "account_provider": account_provider, "position_provider": position_provider}
    engine.dispose()


def _candidate_batch():
    return CreateCandidatesRequest(
        selection_mode=SelectionMode.MANUAL,
        symbols=["RELIANCE"],
        horizon=AnalysisHorizon.INTRADAY,
    )


def _analysis_request(candidate_id):
    return AnalysisRequest(
        candidate_id=candidate_id,
        provider=ProviderName.TRADING_AGENTS,
        analysis_date=date(2026, 10, 30),
        horizon=AnalysisHorizon.INTRADAY,
        analysis_profile_key="INTRADAY_RESEARCH",
        analysis_profile_version="1",
    )


def test_i1_persists_selection_and_idempotent_analysis_lifecycle(i1_workflow):
    async def run():
        batch = await i1_workflow["candidate_service"].create_candidates(_candidate_batch(), owner_id=1)
        candidate = batch.candidates[0]
        request = _analysis_request(candidate.candidate_id)
        first = await i1_workflow["workflow"].request_candidate_analysis(
            candidate.candidate_id, request, owner_id=1, idempotency_key="i1:reliance:2026-10-30"
        )
        duplicate = await i1_workflow["workflow"].request_candidate_analysis(
            candidate.candidate_id, request, owner_id=1, idempotency_key="i1:reliance:2026-10-30"
        )
        result = await i1_workflow["analysis_service"].run_analysis_job(first.analysis_id)
        return candidate, first, duplicate, result

    candidate, first, duplicate, result = asyncio.run(run())

    assert candidate.instrument.analysis_ticker == "RELIANCE.NS"
    assert first.analysis_id == duplicate.analysis_id
    assert first.status.value == "PENDING"
    assert result.status.value == "COMPLETED"
    assert result.source_rating == "Overweight"
    assert i1_workflow["provider"].requests[0].instrument.analysis_ticker == "RELIANCE.NS"
    with i1_workflow["sessions"]() as session:
        jobs = session.execute(text("SELECT analysis_id, status FROM analysis_jobs")).all()
        candidates = session.execute(text("SELECT candidate_id FROM stock_candidates")).all()
        runs = session.execute(text("SELECT analysis_id, result_json FROM analysis_runs")).all()
    assert len(candidates) == len(jobs) == len(runs) == 1
    assert jobs[0].status == "COMPLETED"
    assert runs[0].analysis_id == jobs[0].analysis_id
    assert json.loads(runs[0].result_json)["source_rating"] == "Overweight"


def test_i1_rejects_mismatched_or_unresolved_candidates_before_creating_jobs(i1_workflow):
    async def run():
        batch = await i1_workflow["candidate_service"].create_candidates(_candidate_batch(), owner_id=1)
        candidate = batch.candidates[0]
        class UnresolvedCandidateService:
            async def get_candidate(self, candidate_id, *, owner_id=None):
                return candidate.model_copy(update={
                    "instrument": candidate.instrument.model_copy(update={"analysis_ticker": None})
                })

        workflow = StockSelectionAnalysisWorkflow(
            UnresolvedCandidateService(), i1_workflow["analysis_service"]
        )
        with pytest.raises(CandidateNotReadyForAnalysis):
            await workflow.request_candidate_analysis(
                candidate.candidate_id,
                _analysis_request(candidate.candidate_id),
                owner_id=1,
                idempotency_key="unresolved",
            )
        with pytest.raises(ValueError, match="does not match"):
            await i1_workflow["workflow"].request_candidate_analysis(
                candidate.candidate_id,
                _analysis_request(uuid4()),
                owner_id=1,
                idempotency_key="mismatch",
            )

    asyncio.run(run())
    with i1_workflow["sessions"]() as session:
        assert session.scalar(text("SELECT count(*) FROM analysis_jobs")) == 0


def test_i1_enforces_candidate_owner_scope(i1_workflow):
    async def run():
        batch = await i1_workflow["candidate_service"].create_candidates(_candidate_batch(), owner_id=1)
        with pytest.raises(CandidateNotFoundError):
            await i1_workflow["workflow"].request_candidate_analysis(
                batch.candidates[0].candidate_id,
                _analysis_request(batch.candidates[0].candidate_id),
                owner_id=2,
                idempotency_key="other-user",
            )

    asyncio.run(run())
    with i1_workflow["sessions"]() as session:
        assert session.scalar(text("SELECT count(*) FROM analysis_jobs")) == 0


async def _create_completed_analysis(context, idempotency_key="i2-analysis"):
    batch = await context["candidate_service"].create_candidates(_candidate_batch(), owner_id=1)
    candidate = batch.candidates[0]
    receipt = await context["workflow"].request_candidate_analysis(
        candidate.candidate_id,
        _analysis_request(candidate.candidate_id),
        owner_id=1,
        idempotency_key=idempotency_key,
    )
    return await context["analysis_service"].run_analysis_job(receipt.analysis_id)


def test_i2_decides_from_persisted_normalized_analysis_and_keeps_source_rating(i1_workflow):
    async def run():
        analysis = await _create_completed_analysis(i1_workflow)
        persisted = await i1_workflow["analysis_service"].get_analysis(analysis.analysis_id, owner_id=1)
        decision = await i1_workflow["decision_workflow"].evaluate_entry(
            analysis.analysis_id, owner_id=1, strategy_key=i1_workflow["policy"].key
        )
        return analysis, persisted, decision

    analysis, persisted, decision = asyncio.run(run())

    assert persisted is not None
    assert persisted.source_rating == "Overweight"
    assert persisted.direction is AnalysisDirection.BULLISH
    assert persisted.reports["portfolio_decision"] == "Rating: Overweight"
    assert decision.status is DecisionStatus.BUY_APPROVED
    assert decision.analysis_id == analysis.analysis_id
    assert decision.order_intent is not None
    assert asyncio.run(i1_workflow["decision_service"].get_decision(decision.decision_id, owner_id=1)) == decision


def test_i2_review_rating_and_stale_analysis_fail_closed(i1_workflow):
    async def run_review():
        i1_workflow["provider"].source_rating = "No consensus"
        analysis = await _create_completed_analysis(i1_workflow, "i2-review")
        decision = await i1_workflow["decision_workflow"].evaluate_entry(
            analysis.analysis_id, owner_id=1, strategy_key=i1_workflow["policy"].key
        )
        return analysis, decision

    review_analysis, review_decision = asyncio.run(run_review())
    assert review_analysis.source_rating == "No consensus"
    assert review_analysis.direction is AnalysisDirection.REVIEW
    assert review_decision.status is DecisionStatus.REVIEW_REQUIRED
    assert review_decision.order_intent is None

    async def run_stale():
        i1_workflow["provider"].source_rating = "Buy"
        analysis = await _create_completed_analysis(i1_workflow, "i2-stale")
        stale = analysis.model_copy(update={"completed_at": datetime.now(timezone.utc) - timedelta(hours=2)})
        with i1_workflow["sessions"].begin() as session:
            session.execute(
                text("UPDATE analysis_runs SET result_json=:payload WHERE analysis_id=:analysis_id"),
                {"payload": stale.model_dump_json(), "analysis_id": str(analysis.analysis_id)},
            )
        decision = await i1_workflow["decision_workflow"].evaluate_entry(
            analysis.analysis_id, owner_id=1, strategy_key=i1_workflow["policy"].key
        )
        return decision

    stale_decision = asyncio.run(run_stale())
    assert stale_decision.status is DecisionStatus.REJECTED
    assert "ANALYSIS_STALE" in stale_decision.reason_codes
    assert stale_decision.order_intent is None


def test_i2_does_not_evaluate_missing_or_other_users_analysis(i1_workflow):
    async def run():
        with pytest.raises(AnalysisUnavailable):
            await i1_workflow["decision_workflow"].evaluate_entry(
                uuid4(), owner_id=1, strategy_key=i1_workflow["policy"].key
            )
        analysis = await _create_completed_analysis(i1_workflow, "i2-owner-check")
        with pytest.raises(AnalysisUnavailable):
            await i1_workflow["decision_workflow"].evaluate_entry(
                analysis.analysis_id, owner_id=2, strategy_key=i1_workflow["policy"].key
            )

    asyncio.run(run())
    with i1_workflow["sessions"]() as session:
        assert session.scalar(text("SELECT count(*) FROM trade_decisions")) == 0


def test_i2_pending_analysis_is_not_sent_to_decision_engine(i1_workflow):
    async def run():
        analysis = await _create_completed_analysis(i1_workflow, "i2-pending-result")

        class PendingAnalysisLookup:
            async def get_analysis(self, analysis_id, *, owner_id):
                return analysis.model_copy(update={"status": AnalysisStatus.PENDING})

        class DecisionMustNotRun:
            async def evaluate_entry(self, request, *, owner_id):
                raise AssertionError("Module 3 must not see an incomplete analysis")

        workflow = AnalysisDecisionWorkflow(PendingAnalysisLookup(), DecisionMustNotRun())
        with pytest.raises(AnalysisUnavailable):
            await workflow.evaluate_entry(
                analysis.analysis_id, owner_id=1, strategy_key=i1_workflow["policy"].key
            )

    asyncio.run(run())
    with i1_workflow["sessions"]() as session:
        assert session.scalar(text("SELECT count(*) FROM trade_decisions")) == 0


def test_i3_only_executes_persisted_approved_intent_and_is_idempotent(i1_workflow):
    async def run():
        analysis = await _create_completed_analysis(i1_workflow, "i3-approved")
        decision = await i1_workflow["decision_workflow"].evaluate_entry(
            analysis.analysis_id, owner_id=1, strategy_key=i1_workflow["policy"].key
        )
        first = await i1_workflow["execution_workflow"].execute_decision(
            decision.decision_id, owner_id=1, mode=ExecutionMode.PAPER
        )
        repeat = await i1_workflow["execution_workflow"].execute_decision(
            decision.decision_id, owner_id=1, mode=ExecutionMode.PAPER
        )
        return decision, first, repeat

    decision, first, repeat = asyncio.run(run())
    assert decision.status is DecisionStatus.BUY_APPROVED
    assert first == repeat
    assert first.status is OrderStatus.PARTIALLY_FILLED
    assert first.filled_quantity == 2
    assert first.remaining_quantity == first.requested_quantity - first.filled_quantity
    assert first.execution_mode is ExecutionMode.PAPER
    assert len(i1_workflow["broker"].submit_calls) == 1
    assert asyncio.run(i1_workflow["execution_service"].get_order_status(
        first.tradeai_order_id, owner_id=1
    )) == first
    with i1_workflow["sessions"]() as session:
        assert session.scalar(text("SELECT count(*) FROM execution_orders")) == 1
        assert session.scalar(text("SELECT count(*) FROM execution_order_events")) >= 2


def test_i3_rejected_decisions_and_live_mode_never_reach_broker(i1_workflow):
    async def run():
        i1_workflow["provider"].source_rating = "Hold"
        analysis = await _create_completed_analysis(i1_workflow, "i3-hold")
        decision = await i1_workflow["decision_workflow"].evaluate_entry(
            analysis.analysis_id, owner_id=1, strategy_key=i1_workflow["policy"].key
        )
        with pytest.raises(DecisionNotExecutable):
            await i1_workflow["execution_workflow"].execute_decision(
                decision.decision_id, owner_id=1, mode=ExecutionMode.PAPER
            )

        i1_workflow["provider"].source_rating = "Buy"
        next_analysis = await _create_completed_analysis(i1_workflow, "i3-live-blocked")
        approved = await i1_workflow["decision_workflow"].evaluate_entry(
            next_analysis.analysis_id, owner_id=1, strategy_key=i1_workflow["policy"].key
        )
        with pytest.raises(LiveExecutionDisabled, match="LIVE_TRADING_ENABLED"):
            await i1_workflow["execution_workflow"].execute_decision(
                approved.decision_id, owner_id=1, mode=ExecutionMode.LIVE
            )
        return decision, approved

    decision, approved = asyncio.run(run())
    assert decision.status is DecisionStatus.HOLD
    assert approved.status is DecisionStatus.BUY_APPROVED
    assert i1_workflow["broker"].submit_calls == []
    with i1_workflow["sessions"]() as session:
        assert session.scalar(text("SELECT count(*) FROM execution_orders")) == 0


def test_i3_unknown_submission_is_reconciled_without_blind_resubmission(i1_workflow):
    async def run():
        analysis = await _create_completed_analysis(i1_workflow, "i3-reconcile")
        decision = await i1_workflow["decision_workflow"].evaluate_entry(
            analysis.analysis_id, owner_id=1, strategy_key=i1_workflow["policy"].key
        )
        i1_workflow["broker"].raise_submit = True
        unknown = await i1_workflow["execution_workflow"].execute_decision(
            decision.decision_id, owner_id=1, mode=ExecutionMode.PAPER
        )
        i1_workflow["broker"].raise_submit = False
        reconciled = await i1_workflow["execution_workflow"].reconcile_order(
            unknown.tradeai_order_id, owner_id=1
        )
        repeated = await i1_workflow["execution_workflow"].execute_decision(
            decision.decision_id, owner_id=1, mode=ExecutionMode.PAPER
        )
        return unknown, reconciled, repeated

    unknown, reconciled, repeated = asyncio.run(run())
    assert unknown.status is OrderStatus.UNKNOWN
    assert reconciled.status is OrderStatus.FILLED
    assert reconciled.filled_quantity == reconciled.requested_quantity
    assert repeated == reconciled
    assert len(i1_workflow["broker"].submit_calls) == 1


def test_i4_monitoring_receives_only_confirmed_fill_quantity_and_price(i1_workflow):
    async def run():
        analysis = await _create_completed_analysis(i1_workflow, "i4-partial-fill")
        decision = await i1_workflow["decision_workflow"].evaluate_entry(
            analysis.analysis_id, owner_id=1, strategy_key=i1_workflow["policy"].key
        )
        order = await i1_workflow["execution_workflow"].execute_decision(
            decision.decision_id, owner_id=1, mode=ExecutionMode.PAPER
        )
        i1_workflow["broker"].reconciled_quantity = 2
        i1_workflow["position_provider"].positions[
            (1, "RELIANCE", "2885", "INTRADAY")
        ] = ConfirmedOpenPosition(
            quantity=2,
            average_price=Decimal("100"),
            opened_at=order.submitted_at,
        )
        market = MarketObservation(
            price=Decimal("94"), captured_at=datetime.now(timezone.utc), market_open=True
        )
        rules = MonitorRules(version="i4-stop-v1", stop_loss_price=Decimal("95"))
        result = await i1_workflow["position_workflow"].evaluate_reconciled_execution(
            order.tradeai_order_id,
            owner_id=1,
            market=market,
            rules=rules,
        )
        return order, result

    order, result = asyncio.run(run())
    assert order.filled_quantity == 2
    assert result.action == "EXIT_CANDIDATE"
    assert result.exit_quantity == order.filled_quantity
    assert result.unrealized_pnl == (Decimal("94") - Decimal("100")) * order.filled_quantity
    assert result.is_new_trigger is True
    with i1_workflow["sessions"]() as session:
        assert session.scalar(text("SELECT count(*) FROM position_monitor_triggers")) == 1


def test_i4_unfilled_order_does_not_create_a_monitored_position(i1_workflow):
    async def run():
        analysis = await _create_completed_analysis(i1_workflow, "i4-no-fill")
        decision = await i1_workflow["decision_workflow"].evaluate_entry(
            analysis.analysis_id, owner_id=1, strategy_key=i1_workflow["policy"].key
        )
        i1_workflow["broker"].submit_update = BrokerOrderUpdate(
            broker=i1_workflow["broker"].name,
            status="OPEN",
            broker_order_id="paper-no-fill",
            filled_quantity=0,
            average_fill_price=None,
            updated_at=datetime.now(timezone.utc),
        )
        i1_workflow["broker"].reconciled_quantity = 0
        order = await i1_workflow["execution_workflow"].execute_decision(
            decision.decision_id, owner_id=1, mode=ExecutionMode.PAPER
        )
        with pytest.raises(PositionNotReadyForMonitoring):
            await i1_workflow["position_workflow"].evaluate_reconciled_execution(
                order.tradeai_order_id,
                owner_id=1,
                market=MarketObservation(
                    price=Decimal("94"), captured_at=datetime.now(timezone.utc), market_open=True
                ),
                rules=MonitorRules(version="i4-no-fill-v1", stop_loss_price=Decimal("95")),
            )

    asyncio.run(run())
    assert i1_workflow["position_provider"].calls == []
    with i1_workflow["sessions"]() as session:
        assert session.scalar(text("SELECT count(*) FROM position_monitor_triggers")) == 0


def test_i5_new_stop_trigger_passes_module3_then_module4_and_is_deduplicated(i1_workflow):
    async def run():
        analysis = await _create_completed_analysis(i1_workflow, "i5-stop-exit")
        entry_decision = await i1_workflow["decision_workflow"].evaluate_entry(
            analysis.analysis_id, owner_id=1, strategy_key=i1_workflow["policy"].key
        )
        entry_order = await i1_workflow["execution_workflow"].execute_decision(
            entry_decision.decision_id, owner_id=1, mode=ExecutionMode.PAPER
        )
        i1_workflow["broker"].reconciled_quantity = 2
        i1_workflow["account_provider"].positions = [ConfirmedPosition(
            symbol="RELIANCE",
            security_id="2885",
            quantity=entry_order.filled_quantity,
            average_price=entry_order.average_fill_price,
            market_value=entry_order.filled_quantity * entry_order.average_fill_price,
        )]
        i1_workflow["position_provider"].positions[
            (1, "RELIANCE", "2885", "INTRADAY")
        ] = ConfirmedOpenPosition(
            quantity=entry_order.filled_quantity,
            average_price=entry_order.average_fill_price,
            opened_at=entry_order.submitted_at,
        )
        market = MarketObservation(
            price=Decimal("94"), captured_at=datetime.now(timezone.utc), market_open=True
        )
        rules = MonitorRules(version="i5-exit-v1", stop_loss_price=Decimal("95"))
        evaluation = await i1_workflow["position_workflow"].evaluate_reconciled_execution(
            entry_order.tradeai_order_id,
            owner_id=1,
            market=market,
            rules=rules,
        )
        outcome = await i1_workflow["exit_workflow"].process_exit_candidate(
            evaluation,
            owner_id=1,
            security_id="2885",
            confirmed_open_quantity=entry_order.filled_quantity,
            average_price=entry_order.average_fill_price,
            strategy_key=i1_workflow["policy"].key,
            strategy_version=i1_workflow["policy"].version,
            mode=ExecutionMode.PAPER,
        )
        repeated_evaluation = await i1_workflow["position_workflow"].evaluate_reconciled_execution(
            entry_order.tradeai_order_id,
            owner_id=1,
            market=market,
            rules=rules,
        )
        repeated = await i1_workflow["exit_workflow"].process_exit_candidate(
            repeated_evaluation,
            owner_id=1,
            security_id="2885",
            confirmed_open_quantity=entry_order.filled_quantity,
            average_price=entry_order.average_fill_price,
            strategy_key=i1_workflow["policy"].key,
            strategy_version=i1_workflow["policy"].version,
            mode=ExecutionMode.PAPER,
        )
        return entry_order, evaluation, outcome, repeated_evaluation, repeated

    entry_order, evaluation, outcome, repeated_evaluation, repeated = asyncio.run(run())
    assert evaluation.action == "EXIT_CANDIDATE" and evaluation.is_new_trigger is True
    assert outcome.decision is not None
    assert outcome.decision.status is DecisionStatus.SELL_APPROVED
    assert outcome.decision.order_intent is not None
    assert outcome.decision.order_intent.side.value == "SELL"
    assert outcome.decision.order_intent.quantity == evaluation.exit_quantity
    assert outcome.execution is not None
    assert outcome.execution.status is OrderStatus.FILLED
    assert outcome.execution.execution_mode is ExecutionMode.PAPER
    assert repeated_evaluation.is_new_trigger is False
    assert repeated.deduplicated is True
    assert repeated.decision is None and repeated.execution is None
    assert len(i1_workflow["broker"].submit_calls) == 2  # entry and one approved exit
    with i1_workflow["sessions"]() as session:
        assert session.scalar(text("SELECT count(*) FROM position_monitor_triggers")) == 1
        assert session.scalar(text("SELECT count(*) FROM trade_decisions")) == 2
        assert session.scalar(text("SELECT count(*) FROM execution_orders")) == 2


def test_i5_rejected_or_oversized_exit_trigger_never_reaches_module4(i1_workflow):
    async def run():
        analysis = await _create_completed_analysis(i1_workflow, "i5-rejected-exit")
        entry_decision = await i1_workflow["decision_workflow"].evaluate_entry(
            analysis.analysis_id, owner_id=1, strategy_key=i1_workflow["policy"].key
        )
        entry_order = await i1_workflow["execution_workflow"].execute_decision(
            entry_decision.decision_id, owner_id=1, mode=ExecutionMode.PAPER
        )
        i1_workflow["broker"].reconciled_quantity = 2
        # Deliberately expose fewer confirmed shares to Module 3 than the monitor requests.
        i1_workflow["account_provider"].positions = [ConfirmedPosition(
            symbol="RELIANCE", security_id="2885", quantity=1,
            average_price=Decimal("100"), market_value=Decimal("100"),
        )]
        i1_workflow["position_provider"].positions[
            (1, "RELIANCE", "2885", "INTRADAY")
        ] = ConfirmedOpenPosition(
            quantity=entry_order.filled_quantity,
            average_price=entry_order.average_fill_price,
            opened_at=entry_order.submitted_at,
        )
        evaluation = await i1_workflow["position_workflow"].evaluate_reconciled_execution(
            entry_order.tradeai_order_id,
            owner_id=1,
            market=MarketObservation(
                price=Decimal("94"), captured_at=datetime.now(timezone.utc), market_open=True
            ),
            rules=MonitorRules(version="i5-rejected-v1", stop_loss_price=Decimal("95")),
        )
        before = len(i1_workflow["broker"].submit_calls)
        outcome = await i1_workflow["exit_workflow"].process_exit_candidate(
            evaluation,
            owner_id=1,
            security_id="2885",
            confirmed_open_quantity=entry_order.filled_quantity,
            average_price=entry_order.average_fill_price,
            strategy_key=i1_workflow["policy"].key,
            strategy_version=i1_workflow["policy"].version,
            mode=ExecutionMode.PAPER,
        )
        assert len(i1_workflow["broker"].submit_calls) == before
        return outcome

    outcome = asyncio.run(run())
    assert outcome.decision is not None
    assert outcome.decision.status is DecisionStatus.REJECTED
    assert "REQUEST_EXCEEDS_CONFIRMED_QUANTITY" in outcome.decision.reason_codes
    assert outcome.execution is None
    with i1_workflow["sessions"]() as session:
        assert session.scalar(text("SELECT count(*) FROM execution_orders")) == 1
