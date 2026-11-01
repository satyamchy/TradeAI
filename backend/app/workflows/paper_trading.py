"""Owner-scoped paper lifecycle orchestration over the existing module services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import Field

from app.broker.trading_gateway import gateway_for_user
from app.jobs.schemas import AnalysisJobView
from app.jobs.service import AnalysisJobManager
from app.modules.ai_analysis.service import AIAnalysisService
from app.modules.decision_engine.repository import SqlAlchemyDecisionRepository
from app.modules.decision_engine.schemas import StrategyPolicy
from app.modules.decision_engine.service import DecisionEngineService
from app.modules.execution.brokers import ExistingTradingGatewayAdapter
from app.modules.execution.repository import SqlAlchemyExecutionRepository
from app.modules.execution.service import ExecutionService
from app.modules.position_monitoring.repository import SqlAlchemyTriggerRepository
from app.modules.position_monitoring.service import PositionMonitoringService
from app.modules.stock_selection.service import StockSelectionService
from app.shared.config import Settings, settings
from app.shared.contracts import (
    AnalysisHorizon,
    AnalysisRequest,
    AnalysisResult,
    AnalysisStatus,
    CreateCandidatesRequest,
    DecisionResult,
    DecisionStatus,
    ExecutionMode,
    ExecutionResult,
    ProviderName,
    SelectionMode,
)
from app.shared.contracts import Contract, PositionEvaluation
from app.shared.providers import (
    TradingGatewayAccountRiskProvider,
    TradingGatewayConfirmedPositionProvider,
    TradingGatewayMarketDataProvider,
    build_strategy_policy,
)
from app.workflows.analysis import StockSelectionAnalysisWorkflow
from app.workflows.decision import AnalysisDecisionWorkflow
from app.workflows.execution import DecisionExecutionWorkflow
from app.workflows.exits import PositionExitWorkflow
from app.workflows.monitoring import ExecutionPositionWorkflow
from app.workflows.schemas import PositionExitOutcome


class PaperTradingUnavailable(RuntimeError):
    """Paper workflows are unavailable unless all application gates are safe."""


class IdempotencyKeyConflict(ValueError):
    """A key was reused for a different workflow request."""


class PaperWorkflowStartRequest(Contract):
    symbol: str = Field(min_length=1, max_length=32)


class PaperPositionView(Contract):
    symbol: str
    security_id: str
    product_type: str
    quantity: int
    average_price: Decimal
    current_price: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    market_data_at: datetime | None = None


class PaperWorkflowView(Contract):
    analysis_id: UUID
    candidate_id: UUID
    symbol: str
    stage: str
    analysis_job: AnalysisJobView
    analysis: AnalysisResult | None = None
    decision: DecisionResult | None = None
    entry_order: ExecutionResult | None = None
    exit_orders: list[ExecutionResult] = Field(default_factory=list)
    position: PaperPositionView | None = None
    realized_pnl: Decimal = Decimal("0")
    final_pnl: Decimal | None = None


class PaperReassessmentView(Contract):
    symbol: str
    position_id: UUID
    evaluation: PositionEvaluation
    exit_outcome: PositionExitOutcome | None = None
    realized_pnl: Decimal = Decimal("0")
    final_pnl: Decimal | None = None


@dataclass
class PaperProviderFactories:
    """Composition hooks for real providers and deterministic integration fixtures."""

    gateway: Callable[[dict[str, Any]], Any] = gateway_for_user
    market_data: Callable[[Any], Any] = TradingGatewayMarketDataProvider
    account_risk: Callable[..., Any] | None = None
    confirmed_positions: Callable[..., Any] | None = None
    broker: Callable[[Any], Any] = ExistingTradingGatewayAdapter


class PaperTradingServiceFactory:
    """Build owner-scoped provider graphs from the one app session factory."""

    def __init__(
        self,
        *,
        sessions,
        job_manager: AnalysisJobManager,
        candidates: StockSelectionService,
        analyses: AIAnalysisService,
        analysis_workflow: StockSelectionAnalysisWorkflow,
        config: Settings = settings,
        provider_factories: PaperProviderFactories | None = None,
    ):
        self._sessions = sessions
        self._jobs = job_manager
        self._candidates = candidates
        self._analyses = analyses
        self._analysis_workflow = analysis_workflow
        self._config = config
        self._providers = provider_factories or PaperProviderFactories()
        self._decisions = SqlAlchemyDecisionRepository(sessions)
        self._executions = SqlAlchemyExecutionRepository(sessions)
        self._triggers = SqlAlchemyTriggerRepository(sessions)

    def for_user(self, user: dict[str, Any]) -> "PaperTradingService":
        if self._config.trading_mode.strip().lower() != "paper" or self._config.live_trading_enabled:
            raise PaperTradingUnavailable("Paper workflow is disabled unless live trading remains off")
        gateway = self._providers.gateway(user)
        if str(getattr(gateway, "mode", "")).strip().lower() != "paper":
            raise PaperTradingUnavailable("The configured gateway is not in paper mode")
        owner_id = int(user["id"])
        market = self._providers.market_data(gateway)
        account_factory = self._providers.account_risk
        if account_factory is None:
            accounts = TradingGatewayAccountRiskProvider(
                gateway,
                owner_id=owner_id,
                market_data=market,
                pending_executions=self._executions,
                approved_intents=self._decisions,
                config=self._config,
            )
        else:
            accounts = account_factory(
                gateway=gateway,
                owner_id=owner_id,
                executions=self._executions,
                decisions=self._decisions,
                config=self._config,
            )
        position_factory = self._providers.confirmed_positions
        positions = (
            TradingGatewayConfirmedPositionProvider(gateway, owner_id=owner_id)
            if position_factory is None
            else position_factory(gateway=gateway, owner_id=owner_id)
        )
        policy = build_strategy_policy(self._config)
        decision_service = DecisionEngineService(
            analyses=self._analyses,
            candidates=self._candidates,
            market=market,
            accounts=accounts,
            repository=self._decisions,
            strategies={policy.key: policy},
        )
        broker = self._providers.broker(gateway)
        execution_service = ExecutionService(
            intents=decision_service,
            repository=self._executions,
            broker=broker,
            live_execution_allowed=False,
        )
        monitoring_service = PositionMonitoringService(triggers=self._triggers)
        decision_workflow = AnalysisDecisionWorkflow(self._analyses, decision_service)
        execution_workflow = DecisionExecutionWorkflow(decision_service, execution_service)
        position_workflow = ExecutionPositionWorkflow(
            execution_service, decision_service, monitoring_service, positions
        )
        exit_workflow = PositionExitWorkflow(decision_service, execution_workflow)
        return PaperTradingService(
            owner_id=owner_id,
            gateway=gateway,
            market=market,
            policy=policy,
            jobs=self._jobs,
            candidates=self._candidates,
            analyses=self._analyses,
            analysis_workflow=self._analysis_workflow,
            decision_service=decision_service,
            decision_workflow=decision_workflow,
            execution_service=execution_service,
            execution_workflow=execution_workflow,
            position_workflow=position_workflow,
            exit_workflow=exit_workflow,
        )


class PaperTradingService:
    """Public paper workflow facade. Module decisions and broker checks stay authoritative."""

    def __init__(
        self,
        *,
        owner_id: int,
        gateway,
        market,
        policy: StrategyPolicy,
        jobs: AnalysisJobManager,
        candidates: StockSelectionService,
        analyses: AIAnalysisService,
        analysis_workflow: StockSelectionAnalysisWorkflow,
        decision_service: DecisionEngineService,
        decision_workflow: AnalysisDecisionWorkflow,
        execution_service: ExecutionService,
        execution_workflow: DecisionExecutionWorkflow,
        position_workflow: ExecutionPositionWorkflow,
        exit_workflow: PositionExitWorkflow,
    ):
        self.owner_id = owner_id
        self._gateway = gateway
        self._market = market
        self._policy = policy
        self._jobs = jobs
        self._candidates = candidates
        self._analyses = analyses
        self._analysis_workflow = analysis_workflow
        self._decision_service = decision_service
        self._decision_workflow = decision_workflow
        self._execution_service = execution_service
        self._execution_workflow = execution_workflow
        self._position_workflow = position_workflow
        self._exit_workflow = exit_workflow

    async def start(self, symbol: str, *, idempotency_key: str) -> PaperWorkflowView:
        clean_symbol = symbol.strip().upper()
        if not clean_symbol:
            raise ValueError("symbol is required")
        if not idempotency_key.strip() or len(idempotency_key) > 110:
            raise ValueError("Idempotency-Key must contain 1 to 110 characters")
        scoped_key = f"paper-workflow:{idempotency_key}"
        existing = self._jobs.get_by_idempotency(scoped_key, owner_id=self.owner_id)
        if existing is not None:
            payload = self._jobs.get_request_payload(existing.analysis_id, owner_id=self.owner_id) or {}
            existing_symbol = str(payload.get("candidate", {}).get("instrument", {}).get("symbol", "")).upper()
            if existing_symbol != clean_symbol:
                raise IdempotencyKeyConflict("Idempotency-Key is already bound to a different symbol")
            return await self.get_workflow(existing.analysis_id)

        batch = await self._candidates.create_candidates(
            CreateCandidatesRequest(
                selection_mode=SelectionMode.MANUAL,
                symbols=[clean_symbol],
                horizon=AnalysisHorizon.INTRADAY,
                exchange="NSE",
            ),
            owner_id=self.owner_id,
        )
        if len(batch.candidates) != 1:
            details = "; ".join(item.message for item in batch.rejections)
            raise ValueError(details or "Stock Selection did not produce one valid candidate")
        candidate = batch.candidates[0]
        request = AnalysisRequest(
            candidate_id=candidate.candidate_id,
            provider=ProviderName.TRADING_AGENTS,
            analysis_date=datetime.now(ZoneInfo("Asia/Kolkata")).date(),
            horizon=AnalysisHorizon.INTRADAY,
            analysis_profile_key="INTRADAY_RESEARCH",
            analysis_profile_version="1",
            include_portfolio_context=False,
            checkpoint_enabled=False,
            save_html_report=False,
        )
        await self._analysis_workflow.request_candidate_analysis(
            candidate.candidate_id,
            request,
            owner_id=self.owner_id,
            idempotency_key=scoped_key,
        )
        job = self._jobs.get_by_idempotency(scoped_key, owner_id=self.owner_id)
        if job is None:
            raise RuntimeError("analysis job was not persisted")
        return await self.get_workflow(job.analysis_id)

    async def advance(self, analysis_id: UUID) -> PaperWorkflowView:
        job = self._jobs.get(analysis_id, owner_id=self.owner_id)
        if job is None:
            raise LookupError("paper workflow was not found")
        if job.status is AnalysisStatus.COMPLETED:
            decision = await self._decision_workflow.evaluate_entry(
                analysis_id, owner_id=self.owner_id, strategy_key=self._policy.key
            )
            if decision.status is DecisionStatus.BUY_APPROVED:
                await self._execution_workflow.execute_decision(
                    decision.decision_id,
                    owner_id=self.owner_id,
                    mode=ExecutionMode.PAPER,
                )
        return await self.get_workflow(analysis_id)

    async def get_workflow(self, analysis_id: UUID) -> PaperWorkflowView:
        job = self._jobs.get(analysis_id, owner_id=self.owner_id)
        if job is None:
            raise LookupError("paper workflow was not found")
        payload = self._jobs.get_request_payload(analysis_id, owner_id=self.owner_id) or {}
        candidate_payload = payload.get("candidate") or {}
        candidate_id = UUID(str(candidate_payload.get("candidate_id")))
        symbol = str(candidate_payload.get("instrument", {}).get("symbol", ""))
        analysis = await self._analyses.get_analysis(analysis_id, owner_id=self.owner_id)
        decisions = await self._decision_service.list_decisions(owner_id=self.owner_id)
        decision = await self._decision_service.get_decision_for_analysis(
            analysis_id, owner_id=self.owner_id
        )
        orders = await self._execution_service.list_orders(owner_id=self.owner_id)
        entry_order = None
        exit_orders: list[ExecutionResult] = []
        position_id = decision.order_intent.position_id if decision and decision.order_intent else None
        if decision and decision.order_intent:
            entry_order = next(
                (order for order in orders if order.order_intent_id == decision.order_intent.order_intent_id),
                None,
            )
        for item in decisions:
            intent = item.order_intent
            if (
                intent is not None
                and intent.side.value == "SELL"
                and position_id is not None
                and intent.position_id == position_id
            ):
                order = next((row for row in orders if row.order_intent_id == intent.order_intent_id), None)
                if order is not None:
                    exit_orders.append(order)
        position = await self._position_for(symbol, decision.order_intent.security_id, self._policy.product_type) if (
            decision and decision.order_intent
        ) else None
        realized, final = _calculate_lifecycle_pnl(entry_order, exit_orders, position)
        stage = _stage(job, analysis, decision, entry_order, exit_orders, position)
        return PaperWorkflowView(
            analysis_id=analysis_id,
            candidate_id=candidate_id,
            symbol=symbol,
            stage=stage,
            analysis_job=job,
            analysis=analysis,
            decision=decision,
            entry_order=entry_order,
            exit_orders=exit_orders,
            position=position,
            realized_pnl=realized,
            final_pnl=final,
        )

    async def list_decisions(self, *, analysis_id: UUID | None = None) -> list[DecisionResult]:
        return await self._decision_service.list_decisions(owner_id=self.owner_id, analysis_id=analysis_id)

    async def list_orders(self) -> list[ExecutionResult]:
        return await self._execution_service.list_orders(owner_id=self.owner_id)

    async def reconcile_order(self, order_id: UUID) -> ExecutionResult:
        return await self._execution_workflow.reconcile_order(order_id, owner_id=self.owner_id)

    async def list_positions(self) -> list[PaperPositionView]:
        rows = await self._gateway.get_open_positions()
        result: list[PaperPositionView] = []
        for row in rows:
            quantity = int(row.get("quantity") or 0)
            average = Decimal(str(row.get("average_price") or 0))
            if quantity <= 0 or average <= 0:
                continue
            market_snapshot = await self._market.get_snapshot(str(row.get("symbol") or ""))
            current = market_snapshot.price if market_snapshot is not None else None
            result.append(
                PaperPositionView(
                    symbol=str(row.get("symbol") or "").upper(),
                    security_id=str(row.get("security_id") or ""),
                    product_type=str(row.get("product_type") or "INTRADAY"),
                    quantity=quantity,
                    average_price=average,
                    current_price=current,
                    unrealized_pnl=(current - average) * quantity if current is not None else None,
                    market_data_at=market_snapshot.captured_at if market_snapshot is not None else None,
                )
            )
        return result

    async def reassess(self, symbol: str) -> PaperReassessmentView:
        normalized = symbol.strip().upper()
        positions = await self.list_positions()
        position = next((row for row in positions if row.symbol == normalized), None)
        if position is None:
            raise LookupError("confirmed open paper position was not found")
        decisions = await self._decision_service.list_decisions(owner_id=self.owner_id)
        orders = await self._execution_service.list_orders(owner_id=self.owner_id)
        entries = []
        for decision in decisions:
            intent = decision.order_intent
            if decision.status is not DecisionStatus.BUY_APPROVED or intent is None or intent.symbol != normalized:
                continue
            execution = next((row for row in orders if row.order_intent_id == intent.order_intent_id), None)
            if execution is not None and execution.filled_quantity > 0:
                entries.append((execution.submitted_at, decision, intent, execution))
        if not entries:
            raise LookupError("confirmed position has no persisted approved entry order")
        _, decision, intent, entry_order = max(entries, key=lambda item: item[0])
        evaluation_execution = await self._position_workflow.evaluate_reconciled_execution(
            entry_order.tradeai_order_id,
            owner_id=self.owner_id,
            market=await self._market_observation(normalized),
            rules=_monitor_rules(intent, self._policy),
        )
        if evaluation_execution is None:
            raise LookupError("paper ledger no longer confirms the monitored position")
        outcome: PositionExitOutcome | None = None
        if evaluation_execution.action == "EXIT_CANDIDATE":
            outcome = await self._exit_workflow.process_exit_candidate(
                evaluation_execution,
                owner_id=self.owner_id,
                security_id=intent.security_id,
                confirmed_open_quantity=position.quantity,
                average_price=position.average_price,
                strategy_key=decision.strategy_key,
                strategy_version=decision.strategy_version,
                mode=ExecutionMode.PAPER,
            )
        current_positions = await self.list_positions()
        remaining = next((row for row in current_positions if row.symbol == normalized), None)
        exit_orders = await self._execution_service.list_orders(owner_id=self.owner_id)
        matching_exits = [
            row for row in exit_orders
            if row.order_intent_id != intent.order_intent_id
            and any(
                item.order_intent is not None
                and item.order_intent.order_intent_id == row.order_intent_id
                and item.order_intent.position_id == intent.position_id
                and item.order_intent.side.value == "SELL"
                for item in await self._decision_service.list_decisions(owner_id=self.owner_id)
            )
        ]
        realized, final = _calculate_lifecycle_pnl(entry_order, matching_exits, remaining)
        return PaperReassessmentView(
            symbol=normalized,
            position_id=intent.position_id,
            evaluation=evaluation_execution,
            exit_outcome=outcome,
            realized_pnl=realized,
            final_pnl=final,
        )

    async def _market_observation(self, symbol: str):
        from app.modules.position_monitoring.schemas import MarketObservation

        snapshot = await self._market.get_snapshot(symbol)
        if snapshot is None:
            return MarketObservation(price=None, captured_at=None, market_open=False)
        return MarketObservation(
            price=snapshot.price,
            captured_at=snapshot.captured_at,
            market_open=snapshot.market_open,
        )

    async def _position_for(
        self, symbol: str, security_id: str, product_type: str
    ) -> PaperPositionView | None:
        return next(
            (
                row for row in await self.list_positions()
                if row.symbol == symbol.upper()
                and row.security_id == security_id
                and row.product_type.upper() == product_type.upper()
            ),
            None,
        )


def _monitor_rules(intent, policy: StrategyPolicy):
    from app.modules.position_monitoring.schemas import MonitorRules
    from app.trading.nse_session import now_ist, SQUARE_OFF

    now = now_ist()
    square_off = now.replace(
        hour=SQUARE_OFF.hour,
        minute=SQUARE_OFF.minute,
        second=0,
        microsecond=0,
    )
    return MonitorRules(
        version=f"{policy.key}:{policy.version}",
        stop_loss_price=intent.stop_loss,
        target_price=intent.target,
        square_off_at=square_off,
        max_market_age_seconds=policy.max_market_age_seconds,
    )


def _calculate_lifecycle_pnl(entry, exits, position) -> tuple[Decimal, Decimal | None]:
    if entry is None or entry.filled_quantity <= 0 or entry.average_fill_price is None:
        return Decimal("0"), None
    sell_quantity = 0
    realized = Decimal("0")
    for order in exits:
        if order.filled_quantity <= 0 or order.average_fill_price is None:
            continue
        quantity = min(order.filled_quantity, max(entry.filled_quantity - sell_quantity, 0))
        if quantity <= 0:
            continue
        realized += (order.average_fill_price - entry.average_fill_price) * quantity
        sell_quantity += quantity
    if position is None and sell_quantity >= entry.filled_quantity:
        return realized, realized
    return realized, None


def _stage(job: AnalysisJobView, analysis, decision, entry, exits, position) -> str:
    if job.status is AnalysisStatus.PENDING:
        return "ANALYSIS_PENDING"
    if job.status is AnalysisStatus.RUNNING:
        return "ANALYSIS_RUNNING"
    if job.status is AnalysisStatus.FAILED:
        return "ANALYSIS_FAILED"
    if analysis is None or analysis.status is not AnalysisStatus.COMPLETED:
        return "ANALYSIS_RESULT_UNAVAILABLE"
    if decision is None:
        return "ANALYSIS_COMPLETED"
    if decision.status is not DecisionStatus.BUY_APPROVED:
        return decision.status.value
    if entry is None:
        return "BUY_APPROVED"
    if entry.status.value == "REJECTED":
        return "ENTRY_REJECTED"
    if entry.status.value in {"UNKNOWN", "PENDING", "OPEN", "PARTIALLY_FILLED"}:
        return entry.status.value
    if any(order.status.value == "REJECTED" for order in exits):
        return "EXIT_REJECTED"
    if any(order.status.value == "UNKNOWN" for order in exits):
        return "EXIT_UNKNOWN"
    if position is not None:
        if any(order.filled_quantity > 0 for order in exits):
            return "POSITION_PARTIALLY_CLOSED"
        return "POSITION_OPEN"
    if exits and all(order.status.value == "FILLED" for order in exits):
        return "CLOSED"
    return "POSITION_NOT_CONFIRMED"
