from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware
from itsdangerous import TimestampSigner

from app import db
from app.api.v1.paper_trading import router as paper_router
from app.broker.trading_gateway import TradingGateway
from app.jobs.repository import SqlAlchemyAnalysisJobRepository
from app.jobs.service import AnalysisJobManager
from app.modules.ai_analysis.profiles import default_profile_registry
from app.modules.ai_analysis.repository import SqlAlchemyAnalysisRunRepository
from app.modules.ai_analysis.schemas import AnalysisProviderOutput
from app.modules.ai_analysis.service import AIAnalysisService
from app.modules.decision_engine.schemas import MarketSnapshot
from app.modules.execution.brokers import ExistingTradingGatewayAdapter
from app.modules.execution.schemas import BrokerOrderUpdate
from app.modules.stock_selection.instrument_master import InstrumentResolution
from app.modules.stock_selection.repository import SqlAlchemyCandidateRepository
from app.modules.stock_selection.service import StockSelectionService
from app.shared.config import Settings
from app.shared.contracts import Instrument
from app.shared.database import create_engine_for_database, create_session_factory
from app.shared.migrations import migrate_database
from app.workflows.analysis import StockSelectionAnalysisWorkflow
from app.workflows.paper_trading import PaperProviderFactories, PaperTradingServiceFactory


class FakeInstrumentResolver:
    def resolve(self, symbol: str, exchange: str) -> InstrumentResolution:
        return InstrumentResolution(
            instrument=Instrument(
                symbol=symbol,
                exchange=exchange,
                trading_symbol=symbol,
                analysis_ticker=f"{symbol}.NS",
                security_id="2885",
                segment="NSE_EQ",
            ),
            mapping_source="END_TO_END_FIXTURE",
            resolved_at=datetime.now(timezone.utc),
        )


class FakeAnalysisProvider:
    version = "paper-test-provider"

    def __init__(self):
        self.calls = 0

    async def analyze(self, request):
        self.calls += 1
        return AnalysisProviderOutput(
            provider_version=self.version,
            source_rating="Buy",
            reports={"portfolio_decision": "fixture bullish result"},
        )


class FixtureMarketProvider:
    def __init__(self):
        self.price = Decimal("100")
        self.captured_at: datetime | None = None

    async def get_snapshot(self, symbol: str):
        captured_at = self.captured_at or datetime.now(timezone.utc)
        return MarketSnapshot(
            symbol=symbol,
            price=self.price,
            captured_at=captured_at,
            market_open=True,
        )


class PartialPaperBroker:
    name = "paper-fixture-partial"

    def __init__(self, gateway, quantity: int = 5):
        self.gateway = gateway
        self.quantity = quantity
        self.submit_calls = 0

    async def submit(self, intent, *, mode):
        self.submit_calls += 1
        fill_quantity = min(self.quantity, intent.quantity)
        raw = await self.gateway.place_tagged_order(
            intent.symbol,
            intent.security_id,
            intent.side.value,
            fill_quantity,
            float(intent.reference_price or intent.limit_price),
            intent.product_type,
            hashlib.sha256(intent.idempotency_key.encode("utf-8")).hexdigest()[:16],
        )
        return BrokerOrderUpdate(
            broker=self.name,
            status="PART_TRADED",
            broker_order_id=raw["order_id"],
            filled_quantity=fill_quantity,
            average_fill_price=Decimal(str(raw["price"])),
            updated_at=datetime.now(timezone.utc),
        )

    async def get_order_status(self, order):
        return await ExistingTradingGatewayAdapter(self.gateway).get_order_status(order)

    async def cancel_order(self, order):
        return await ExistingTradingGatewayAdapter(self.gateway).cancel_order(order)


class AcceptThenTimeoutPaperBroker(ExistingTradingGatewayAdapter):
    """Simulate a lost response after the real temporary paper ledger filled."""

    def __init__(self, gateway):
        super().__init__(gateway)
        self.gateway = gateway
        self.submit_calls = 0

    async def submit(self, intent, *, mode):
        self.submit_calls += 1
        await self.gateway.place_tagged_order(
            intent.symbol,
            intent.security_id,
            intent.side.value,
            intent.quantity,
            float(intent.reference_price or intent.limit_price),
            intent.product_type,
            hashlib.sha256(intent.idempotency_key.encode("utf-8")).hexdigest()[:16],
        )
        raise TimeoutError("simulated response lost after paper fill")


class RejectingPaperBroker:
    name = "paper-fixture-rejected"

    async def submit(self, intent, *, mode):
        return BrokerOrderUpdate(
            broker=self.name,
            status="REJECTED",
            broker_order_id="paper-rejected-1",
            filled_quantity=0,
            average_fill_price=None,
            updated_at=datetime.now(timezone.utc),
            rejection_reason="fixture rejection",
        )

    async def get_order_status(self, order):
        return await ExistingTradingGatewayAdapter(self.gateway).get_order_status(order)

    async def cancel_order(self, order):
        return await ExistingTradingGatewayAdapter(self.gateway).cancel_order(order)

    def __init__(self, gateway):
        self.gateway = gateway


def _make_context(tmp_path: Path, monkeypatch, *, starting_balance=100_000.0, broker_factory=None):
    database = tmp_path / "paper-lifecycle.sqlite"
    migrate_database(database, backup_dir=tmp_path / "backups")
    engine = create_engine_for_database(database)
    sessions = create_session_factory(engine)
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, username, password_hash, role, disabled, automation_state, "
                "automation_methods, created_at) VALUES (1, 'paper-e2e', 'unused', 'trader', 0, "
                "'off', '[]', :now)"
            ),
            {"now": now},
        )

    config = Settings(
        database_path=str(database),
        trading_mode="paper",
        live_trading_enabled=False,
        paper_starting_balance_inr=starting_balance,
        paper_ledger_path=str(tmp_path / "paper-ledger.json"),
        paper_ledger_dir=str(tmp_path / "paper-ledgers"),
        capital_per_trade_pct=0.20,
        cash_reserve_pct=0.10,
        take_profit_pct=1.5,
        stop_loss_pct=1.0,
        max_daily_loss_inr=2_000.0,
        max_positions=4,
    )
    monkeypatch.setattr(db, "get_risk_settings", lambda: None)
    candidates = StockSelectionService(SqlAlchemyCandidateRepository(sessions), FakeInstrumentResolver())
    jobs = AnalysisJobManager(SqlAlchemyAnalysisJobRepository(sessions))
    analysis_provider = FakeAnalysisProvider()
    analyses = AIAnalysisService(
        jobs=jobs,
        repository=SqlAlchemyAnalysisRunRepository(sessions),
        candidates=candidates,
        profiles=default_profile_registry(config),
        provider=analysis_provider,
    )
    analysis_workflow = StockSelectionAnalysisWorkflow(candidates, analyses)
    gateway = TradingGateway(
        mode="paper",
        ledger_path=str(tmp_path / "paper-ledger.json"),
        starting_balance_inr=starting_balance,
    )
    market = FixtureMarketProvider()
    provider_factories = PaperProviderFactories(
        gateway=lambda user: gateway,
        market_data=lambda selected_gateway: market,
        broker=broker_factory or ExistingTradingGatewayAdapter,
    )
    factory = PaperTradingServiceFactory(
        sessions=sessions,
        job_manager=jobs,
        candidates=candidates,
        analyses=analyses,
        analysis_workflow=analysis_workflow,
        config=config,
        provider_factories=provider_factories,
    )
    user = {"id": 1, "username": "paper-e2e", "role": "trader", "disabled": 0}
    service = factory.for_user(user)
    return {
        "engine": engine,
        "sessions": sessions,
        "config": config,
        "jobs": jobs,
        "provider": analysis_provider,
        "analyses": analyses,
        "gateway": gateway,
        "market": market,
        "factory": factory,
        "service": service,
        "user": user,
    }


def _process_analysis(context, analysis_id):
    return asyncio.run(context["jobs"].process_next(context["analyses"].handle_job, analysis_id=analysis_id))


def test_paper_lifecycle_uses_public_api_real_database_and_paper_ledger(tmp_path, monkeypatch):
    context = _make_context(tmp_path, monkeypatch)
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-session-secret", session_cookie="tradex_session")
    app.include_router(paper_router, prefix="/api/v1")
    app.state.paper_trading_service_factory = context["factory"]
    monkeypatch.setattr("app.shared.security.db.get_user", lambda user_id: context["user"] if user_id == 1 else None)
    cookie_data = base64.b64encode(json.dumps({"user_id": 1}).encode("utf-8"))
    cookie = TimestampSigner("test-session-secret").sign(cookie_data).decode("utf-8")
    client = TestClient(app)
    client.cookies.set("tradex_session", cookie)
    try:
        started = client.post(
            "/api/v1/paper/workflows",
            json={"symbol": "RELIANCE"},
            headers={"Idempotency-Key": "lifecycle-one"},
        )
        assert started.status_code == 202, started.text
        initial = started.json()
        analysis_id = initial["analysis_id"]
        assert initial["stage"] == "ANALYSIS_PENDING"

        duplicate = client.post(
            "/api/v1/paper/workflows",
            json={"symbol": "RELIANCE"},
            headers={"Idempotency-Key": "lifecycle-one"},
        )
        assert duplicate.status_code == 202
        assert duplicate.json()["analysis_id"] == analysis_id
        with context["sessions"]() as session:
            assert session.scalar(text("SELECT count(*) FROM analysis_jobs")) == 1
            assert session.scalar(text("SELECT count(*) FROM stock_candidates")) == 1

        completed_job = _process_analysis(context, UUID(analysis_id))
        assert completed_job.status.value == "COMPLETED"
        advanced = client.post(f"/api/v1/paper/workflows/{analysis_id}/advance")
        assert advanced.status_code == 200, advanced.text
        entry_view = advanced.json()
        assert entry_view["stage"] == "POSITION_OPEN"
        assert entry_view["decision"]["status"] == "BUY_APPROVED"
        assert entry_view["entry_order"]["status"] == "FILLED"
        assert entry_view["position"]["quantity"] > 0
        assert context["provider"].calls == 1

        repeated = client.post(f"/api/v1/paper/workflows/{analysis_id}/advance")
        assert repeated.status_code == 200
        assert repeated.json()["entry_order"]["tradeai_order_id"] == entry_view["entry_order"]["tradeai_order_id"]
        assert len(asyncio.run(context["gateway"].get_orders())) == 1

        assert client.get("/api/v1/paper/decisions").status_code == 200
        assert len(client.get("/api/v1/paper/orders").json()) == 1
        assert len(client.get("/api/v1/paper/positions").json()) == 1

        context["market"].price = Decimal("102")
        reassessed = client.post("/api/v1/paper/positions/RELIANCE/reassess")
        assert reassessed.status_code == 200, reassessed.text
        exit_payload = reassessed.json()
        assert exit_payload["evaluation"]["action"] == "EXIT_CANDIDATE"
        assert exit_payload["exit_outcome"]["decision"]["status"] == "SELL_APPROVED"
        assert exit_payload["exit_outcome"]["execution"]["status"] == "FILLED"
        assert Decimal(exit_payload["final_pnl"]) == Decimal(exit_payload["realized_pnl"])
        assert client.get("/api/v1/paper/positions").json() == []

        closed = client.get(f"/api/v1/paper/workflows/{analysis_id}")
        assert closed.status_code == 200
        assert closed.json()["stage"] == "CLOSED"
        assert Decimal(closed.json()["final_pnl"]) == Decimal(exit_payload["final_pnl"])
        with context["sessions"]() as session:
            assert session.scalar(text("SELECT count(*) FROM trade_decisions")) == 2
            assert session.scalar(text("SELECT count(*) FROM execution_orders")) == 2
            assert session.scalar(text("SELECT count(*) FROM position_monitor_triggers")) == 1
        assert len(asyncio.run(context["gateway"].get_orders())) == 2
        assert round(awaitable_balance(context["gateway"])) == 101_800
    finally:
        client.close()
        context["engine"].dispose()


def awaitable_balance(gateway) -> float:
    return asyncio.run(gateway.get_available_balance_inr())


def test_stale_market_and_insufficient_capital_fail_before_execution(tmp_path, monkeypatch):
    stale_context = _make_context(tmp_path / "stale", monkeypatch)
    try:
        started = asyncio.run(stale_context["service"].start("RELIANCE", idempotency_key="stale"))
        _process_analysis(stale_context, started.analysis_id)
        stale_context["market"].captured_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        result = asyncio.run(stale_context["service"].advance(started.analysis_id))
        assert result.decision is not None
        assert result.decision.status.value == "REJECTED"
        assert "MARKET_DATA_STALE" in result.decision.reason_codes
        assert asyncio.run(stale_context["gateway"].get_orders()) == []
    finally:
        stale_context["engine"].dispose()

    poor_context = _make_context(tmp_path / "poor", monkeypatch, starting_balance=50)
    try:
        started = asyncio.run(poor_context["service"].start("RELIANCE", idempotency_key="poor"))
        _process_analysis(poor_context, started.analysis_id)
        result = asyncio.run(poor_context["service"].advance(started.analysis_id))
        assert result.decision is not None
        assert result.decision.status.value == "REJECTED"
        assert result.entry_order is None
        assert asyncio.run(poor_context["gateway"].get_orders()) == []
    finally:
        poor_context["engine"].dispose()


def test_concurrent_advances_create_one_decision_and_one_paper_order(tmp_path, monkeypatch):
    context = _make_context(tmp_path, monkeypatch)
    try:
        started = asyncio.run(context["service"].start("RELIANCE", idempotency_key="parallel"))
        _process_analysis(context, started.analysis_id)

        async def run_concurrently():
            return await asyncio.gather(
                context["service"].advance(started.analysis_id),
                context["service"].advance(started.analysis_id),
            )

        first, second = asyncio.run(run_concurrently())
        assert first.decision is not None and second.decision is not None
        assert first.decision.decision_id == second.decision.decision_id
        assert first.entry_order is not None and second.entry_order is not None
        assert first.entry_order.tradeai_order_id == second.entry_order.tradeai_order_id
        assert len(asyncio.run(context["gateway"].get_orders())) == 1
        with context["sessions"]() as session:
            assert session.scalar(text("SELECT count(*) FROM trade_decisions")) == 1
            assert session.scalar(text("SELECT count(*) FROM execution_orders")) == 1
    finally:
        context["engine"].dispose()


def test_partial_fill_is_confirmed_and_survives_reconciliation(tmp_path, monkeypatch):
    context = _make_context(
        tmp_path,
        monkeypatch,
        broker_factory=lambda gateway: PartialPaperBroker(gateway, quantity=5),
    )
    try:
        started = asyncio.run(context["service"].start("RELIANCE", idempotency_key="partial"))
        _process_analysis(context, started.analysis_id)
        result = asyncio.run(context["service"].advance(started.analysis_id))
        assert result.entry_order is not None
        assert result.entry_order.status.value == "PARTIALLY_FILLED"
        assert result.entry_order.filled_quantity == 5
        assert result.position is not None and result.position.quantity == 5
        reconciled = asyncio.run(context["service"].reconcile_order(result.entry_order.tradeai_order_id))
        assert reconciled.filled_quantity == 5
        assert reconciled.status.value == "PARTIALLY_FILLED"
        assert len(asyncio.run(context["gateway"].get_orders())) == 1
    finally:
        context["engine"].dispose()


def test_rejected_order_is_persisted_without_a_position(tmp_path, monkeypatch):
    context = _make_context(tmp_path, monkeypatch, broker_factory=RejectingPaperBroker)
    try:
        started = asyncio.run(context["service"].start("RELIANCE", idempotency_key="rejected"))
        _process_analysis(context, started.analysis_id)
        result = asyncio.run(context["service"].advance(started.analysis_id))
        assert result.stage == "ENTRY_REJECTED"
        assert result.entry_order is not None
        assert result.entry_order.status.value == "REJECTED"
        assert result.position is None
        assert asyncio.run(context["gateway"].get_orders()) == []
    finally:
        context["engine"].dispose()


def test_unknown_paper_submission_reconciles_after_service_restart(tmp_path, monkeypatch):
    context = _make_context(
        tmp_path,
        monkeypatch,
        broker_factory=AcceptThenTimeoutPaperBroker,
    )
    try:
        started = asyncio.run(context["service"].start("RELIANCE", idempotency_key="restart"))
        _process_analysis(context, started.analysis_id)
        uncertain = asyncio.run(context["service"].advance(started.analysis_id))
        assert uncertain.entry_order is not None
        assert uncertain.entry_order.status.value == "UNKNOWN"
        assert len(asyncio.run(context["gateway"].get_orders())) == 1

        restarted_gateway = TradingGateway(
            mode="paper",
            ledger_path=str(tmp_path / "paper-ledger.json"),
            starting_balance_inr=100_000,
        )
        restarted_factory = PaperProviderFactories(
            gateway=lambda user: restarted_gateway,
            market_data=lambda selected_gateway: context["market"],
        )
        restarted = PaperTradingServiceFactory(
            sessions=context["sessions"],
            job_manager=context["jobs"],
            candidates=context["factory"]._candidates,
            analyses=context["analyses"],
            analysis_workflow=context["factory"]._analysis_workflow,
            config=context["config"],
            provider_factories=restarted_factory,
        ).for_user(context["user"])
        reconciled = asyncio.run(restarted.reconcile_order(uncertain.entry_order.tradeai_order_id))
        assert reconciled.status.value == "FILLED"
        recovered = asyncio.run(restarted.get_workflow(started.analysis_id))
        assert recovered.stage == "POSITION_OPEN"
        assert recovered.position is not None
        assert len(asyncio.run(restarted_gateway.get_orders())) == 1
    finally:
        context["engine"].dispose()
