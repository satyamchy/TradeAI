"""Deterministic decision and risk service; no AI or broker imports."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Protocol
from uuid import UUID, uuid5

from app.modules.decision_engine.repository import DecisionRepository
from app.modules.decision_engine.schemas import (
    AccountRiskSnapshot,
    DecisionEvaluationContext,
    DecisionResult,
    DecisionStatus,
    EvaluateTradeRequest,
    ExitEvaluationRequest,
    MarketSnapshot,
    StrategyPolicy,
)
from app.shared.contracts import (
    AnalysisDirection,
    AnalysisResult,
    AnalysisStatus,
    ApprovedOrderIntent,
    Candidate,
    OrderSide,
    OrderType,
)

_INTENT_NAMESPACE = UUID("b24202c8-39c2-4d56-a4d0-df7e6c8f89af")


class AnalysisLookup(Protocol):
    async def get_analysis(self, analysis_id: UUID, *, owner_id: int) -> AnalysisResult | None: ...


class CandidateLookup(Protocol):
    async def get_candidate(self, candidate_id: UUID, *, owner_id: int) -> Candidate | None: ...


class MarketSnapshotProvider(Protocol):
    async def get_snapshot(self, symbol: str) -> MarketSnapshot | None: ...


class AccountRiskProvider(Protocol):
    async def get_snapshot(self, *, owner_id: int) -> AccountRiskSnapshot | None: ...


class DecisionEngineError(RuntimeError):
    """Base error for unavailable decision inputs or unknown strategies."""


class DecisionInputsUnavailable(DecisionEngineError):
    """A required analysis, market, account, or candidate input is unavailable."""


class UnknownStrategy(DecisionEngineError):
    """The requested strategy is not registered."""


class DecisionEngineService:
    """Evaluates long-only entries and bounded exits using injected snapshots."""

    def __init__(
        self,
        *,
        analyses: AnalysisLookup,
        candidates: CandidateLookup,
        market: MarketSnapshotProvider,
        accounts: AccountRiskProvider,
        repository: DecisionRepository,
        strategies: dict[str, StrategyPolicy],
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self._analyses = analyses
        self._candidates = candidates
        self._market = market
        self._accounts = accounts
        self._repository = repository
        self._strategies = dict(strategies)
        self._clock = clock

    async def evaluate_entry(self, request: EvaluateTradeRequest, *, owner_id: int) -> DecisionResult:
        if request.requested_action.strip().upper() != "ENTRY":
            raise DecisionEngineError("evaluate_entry accepts ENTRY requests only")
        analysis = await self._analyses.get_analysis(request.analysis_id, owner_id=owner_id)
        if analysis is None:
            raise DecisionInputsUnavailable("Completed analysis was not found")
        candidate = await self._candidates.get_candidate(analysis.candidate_id, owner_id=owner_id)
        if candidate is None:
            raise DecisionInputsUnavailable("Candidate was not found")
        policy = self._policy(request.strategy_key)
        market = await self._market.get_snapshot(candidate.instrument.symbol)
        account = await self._accounts.get_snapshot(owner_id=owner_id)
        if market is None or account is None:
            raise DecisionInputsUnavailable("Fresh market and account snapshots are required")
        evaluated_at = _aware(self._clock(), "decision clock")
        context = DecisionEvaluationContext(
            analysis=analysis,
            market=market,
            account=account,
            policy=policy,
            evaluated_at=evaluated_at,
            security_id=candidate.instrument.security_id,
            exchange=candidate.instrument.exchange,
            segment=candidate.instrument.segment or "NSE_EQ",
        )
        codes = _entry_rejections(context, candidate.instrument.symbol)
        status = _signal_status(analysis) if not codes else DecisionStatus.REJECTED
        if status is not DecisionStatus.BUY_APPROVED:
            if status is DecisionStatus.REJECTED and not codes:
                codes.append("SIGNAL_NOT_BUY")
            return self._persist(
                _result(
                    analysis_id=analysis.analysis_id,
                    symbol=candidate.instrument.symbol,
                    status=status,
                    policy=policy,
                    codes=codes,
                    evaluated_at=evaluated_at,
                    market_at=market.captured_at,
                ),
                owner_id,
                _decision_key("ENTRY", owner_id, analysis, context),
            )
        intent, size_codes = _size_entry(context, candidate.instrument.symbol, evaluated_at)
        if intent is None:
            return self._persist(
                _result(
                    analysis_id=analysis.analysis_id,
                    symbol=candidate.instrument.symbol,
                    status=DecisionStatus.REJECTED,
                    policy=policy,
                    codes=size_codes,
                    evaluated_at=evaluated_at,
                    market_at=market.captured_at,
                ),
                owner_id,
                _decision_key("ENTRY", owner_id, analysis, context),
            )
        key = _decision_key("ENTRY", owner_id, analysis, context)
        intent = intent.model_copy(
            update={
                "decision_id": uuid5(_INTENT_NAMESPACE, key),
                "order_intent_id": uuid5(_INTENT_NAMESPACE, "intent:" + key),
                "idempotency_key": "decision:" + key,
            }
        )
        return self._persist(
            _result(
                analysis_id=analysis.analysis_id,
                symbol=candidate.instrument.symbol,
                status=DecisionStatus.BUY_APPROVED,
                policy=policy,
                codes=["ENTRY_RISK_CHECKS_PASSED"],
                evaluated_at=evaluated_at,
                market_at=market.captured_at,
                intent=intent,
            ),
            owner_id,
            key,
        )

    async def evaluate_exit(self, request: ExitEvaluationRequest, *, owner_id: int) -> DecisionResult:
        policy = self._policy(request.strategy_key)
        if policy.version != request.strategy_version:
            raise UnknownStrategy("Exit request strategy version is not registered")
        market = await self._market.get_snapshot(request.symbol)
        account = await self._accounts.get_snapshot(owner_id=owner_id)
        if market is None or account is None:
            raise DecisionInputsUnavailable("Fresh market and account snapshots are required for exits")
        evaluated_at = _aware(self._clock(), "decision clock")
        codes = _exit_rejections(request, market, account, policy, evaluated_at)
        decision_key = _exit_decision_key(owner_id, request, market, account, policy)
        if codes:
            result = _result(
                analysis_id=None,
                symbol=request.symbol,
                status=DecisionStatus.REJECTED,
                policy=policy,
                codes=codes,
                evaluated_at=evaluated_at,
                market_at=market.captured_at,
            )
            return self._persist(result, owner_id, decision_key)
        quantity = min(request.requested_quantity or request.confirmed_open_quantity, request.confirmed_open_quantity)
        intent = ApprovedOrderIntent(
            order_intent_id=uuid5(_INTENT_NAMESPACE, "intent:" + decision_key),
            decision_id=uuid5(_INTENT_NAMESPACE, decision_key),
            symbol=request.symbol,
            security_id=request.security_id,
            side=OrderSide.SELL,
            quantity=quantity,
            order_type=OrderType.MARKET,
            max_risk_amount=Decimal("0"),
            idempotency_key="decision:" + decision_key,
            expires_at=evaluated_at + timedelta(seconds=policy.intent_ttl_seconds),
            reference_price=market.price,
            product_type=policy.product_type,
            intent_kind="EXIT",
            position_id=request.position_id,
        )
        result = _result(
            analysis_id=None,
            symbol=request.symbol,
            status=DecisionStatus.SELL_APPROVED,
            policy=policy,
            codes=["EXIT_WITHIN_CONFIRMED_QUANTITY", "AI_NOT_REQUIRED_FOR_EXIT"],
            evaluated_at=evaluated_at,
            market_at=market.captured_at,
            intent=intent,
        )
        return self._persist(result, owner_id, decision_key)

    async def get_decision(self, decision_id: UUID, *, owner_id: int) -> DecisionResult | None:
        return self._repository.get(decision_id, owner_id=owner_id)

    async def get_approved_intent(self, intent_id: UUID, *, owner_id: int) -> ApprovedOrderIntent | None:
        """Read only a still-approved persisted intent for the execution boundary."""
        return self._repository.get_approved_intent(intent_id, owner_id=owner_id)

    def _persist(self, result: DecisionResult, owner_id: int, key: str) -> DecisionResult:
        decision_id = uuid5(_INTENT_NAMESPACE, key)
        intent = result.order_intent
        if intent is not None:
            intent = intent.model_copy(
                update={
                    "decision_id": decision_id,
                    "order_intent_id": uuid5(_INTENT_NAMESPACE, "intent:" + key),
                    "idempotency_key": "decision:" + key,
                }
            )
        result = result.model_copy(update={"decision_id": decision_id, "order_intent": intent})
        return self._repository.save(result, owner_id=owner_id, decision_key=key)

    def _policy(self, key: str) -> StrategyPolicy:
        try:
            return self._strategies[key]
        except KeyError as exc:
            raise UnknownStrategy(f"Strategy {key!r} is not registered") from exc


def _entry_rejections(context: DecisionEvaluationContext, expected_symbol: str) -> list[str]:
    analysis, market, account, policy, now = (
        context.analysis,
        context.market,
        context.account,
        context.policy,
        context.evaluated_at,
    )
    reasons: list[str] = []
    if analysis.status is not AnalysisStatus.COMPLETED:
        reasons.append("ANALYSIS_NOT_COMPLETED")
    if analysis.completed_at is None or not _is_fresh(analysis.completed_at, now, policy.max_analysis_age_seconds):
        reasons.append("ANALYSIS_STALE")
    if analysis.symbol.upper() != expected_symbol.upper() or market.symbol.upper() != expected_symbol.upper():
        reasons.append("SYMBOL_MISMATCH")
    if not _is_fresh(market.captured_at, now, policy.max_market_age_seconds):
        reasons.append("MARKET_DATA_STALE")
    if not _is_fresh(account.captured_at, now, policy.max_account_age_seconds):
        reasons.append("ACCOUNT_DATA_STALE")
    if not market.market_open:
        reasons.append("MARKET_CLOSED")
    if not context.security_id:
        reasons.append("SECURITY_ID_UNRESOLVED")
    if account.kill_switch_enabled:
        reasons.append("KILL_SWITCH_ENABLED")
    if account.daily_loss >= policy.max_daily_loss:
        reasons.append("DAILY_LOSS_LIMIT_REACHED")
    if account.available_funds <= 0:
        reasons.append("NO_AVAILABLE_FUNDS")
    if any(item.symbol.upper() == expected_symbol.upper() for item in account.confirmed_positions):
        reasons.append("DUPLICATE_POSITION")
    if any(item.upper() == expected_symbol.upper() for item in account.pending_symbols):
        reasons.append("PENDING_ORDER_EXISTS")
    if len(account.confirmed_positions) >= policy.max_positions:
        reasons.append("MAX_POSITIONS_REACHED")
    return reasons


def _signal_status(analysis: AnalysisResult) -> DecisionStatus:
    if analysis.status is not AnalysisStatus.COMPLETED:
        return DecisionStatus.REJECTED
    if analysis.direction is AnalysisDirection.REVIEW:
        return DecisionStatus.REVIEW_REQUIRED
    if analysis.direction is AnalysisDirection.NEUTRAL:
        return DecisionStatus.HOLD
    if analysis.direction is AnalysisDirection.BEARISH:
        return DecisionStatus.REJECTED
    return DecisionStatus.BUY_APPROVED


def _size_entry(
    context: DecisionEvaluationContext, symbol: str, evaluated_at: datetime
) -> tuple[ApprovedOrderIntent | None, list[str]]:
    price = context.market.price
    policy = context.policy
    stop = _money(price * (Decimal("1") - policy.stop_loss_pct / Decimal("100")))
    target = _money(price * (Decimal("1") + policy.target_pct / Decimal("100")))
    risk_per_share = price - stop
    if stop <= 0 or risk_per_share <= 0:
        return None, ["INVALID_STOP_LOSS"]
    current_symbol_exposure = sum(
        (position.market_value for position in context.account.confirmed_positions
         if position.symbol.upper() == symbol.upper()),
        Decimal("0"),
    )
    cash_cap = min(
        context.account.available_funds,
        policy.max_order_value,
        policy.max_symbol_exposure - current_symbol_exposure,
        policy.max_total_exposure - context.account.total_exposure,
    )
    if cash_cap <= 0:
        return None, ["EXPOSURE_LIMIT_REACHED"]
    risk_budget = min(policy.max_risk_amount, context.account.available_funds * policy.risk_budget_fraction)
    quantity_by_risk = int((risk_budget / risk_per_share).to_integral_value(rounding=ROUND_DOWN))
    quantity_by_value = int((cash_cap / price).to_integral_value(rounding=ROUND_DOWN))
    quantity = min(quantity_by_risk, quantity_by_value)
    if quantity <= 0:
        return None, ["POSITION_SIZE_ZERO"]
    intent = ApprovedOrderIntent(
        order_intent_id=uuid5(_INTENT_NAMESPACE, "pending-intent"),
        decision_id=uuid5(_INTENT_NAMESPACE, "pending-decision"),
        symbol=symbol,
        security_id=context.security_id or "",
        side=OrderSide.BUY,
        quantity=quantity,
        order_type=OrderType(context.policy.order_type),
        limit_price=price if policy.order_type == "LIMIT" else None,
        stop_loss=stop,
        target=target,
        max_risk_amount=_money(risk_per_share * quantity),
        idempotency_key="pending",
        expires_at=evaluated_at + timedelta(seconds=policy.intent_ttl_seconds),
        reference_price=price,
        exchange=context.exchange,
        segment=context.segment,
        product_type=policy.product_type,
    )
    return intent, []


def _exit_rejections(
    request: ExitEvaluationRequest,
    market: MarketSnapshot,
    account: AccountRiskSnapshot,
    policy: StrategyPolicy,
    now: datetime,
) -> list[str]:
    reason: list[str] = []
    if market.symbol.upper() != request.symbol.upper():
        reason.append("SYMBOL_MISMATCH")
    if not _is_fresh(market.captured_at, now, policy.max_market_age_seconds):
        reason.append("MARKET_DATA_STALE")
    if not _is_fresh(account.captured_at, now, policy.max_account_age_seconds):
        reason.append("ACCOUNT_DATA_STALE")
    if not market.market_open:
        reason.append("MARKET_CLOSED")
    position = next(
        (item for item in account.confirmed_positions if item.symbol.upper() == request.symbol.upper()), None
    )
    if position is None:
        reason.append("NO_CONFIRMED_OPEN_POSITION")
    else:
        if position.security_id != request.security_id:
            reason.append("SECURITY_ID_MISMATCH")
        if request.confirmed_open_quantity > position.quantity:
            reason.append("REQUEST_EXCEEDS_CONFIRMED_QUANTITY")
        if request.requested_quantity and request.requested_quantity > position.quantity:
            reason.append("EXIT_QUANTITY_EXCEEDS_CONFIRMED_QUANTITY")
    return reason


def _decision_key(kind: str, owner_id: int, analysis: AnalysisResult, context: DecisionEvaluationContext) -> str:
    body = {
        "kind": kind,
        "owner": owner_id,
        "analysis": str(analysis.analysis_id),
        "analysis_status": analysis.status.value,
        "analysis_direction": analysis.direction.value,
        "analysis_rating": analysis.source_rating,
        "analysis_completed": _time_string(analysis.completed_at),
        "symbol": context.market.symbol.upper(),
        "price": str(context.market.price),
        "market_at": _time_string(context.market.captured_at),
        "market_open": context.market.market_open,
        "account": context.account.model_dump(mode="json"),
        "policy": context.policy.model_dump(mode="json"),
        "security_id": context.security_id,
        "exchange": context.exchange,
        "segment": context.segment,
    }
    return _hash(body)


def _exit_decision_key(owner_id, request, market, account, policy) -> str:
    return _hash({
        "kind": "EXIT",
        "owner": owner_id,
        "request": request.model_dump(mode="json"),
        "market": market.model_dump(mode="json"),
        "account": account.model_dump(mode="json"),
        "policy": policy.model_dump(mode="json"),
    })


def _result(
    *, analysis_id, symbol, status, policy, codes, evaluated_at, market_at, intent=None
) -> DecisionResult:
    return DecisionResult(
        decision_id=uuid5(_INTENT_NAMESPACE, "decision:" + str(analysis_id) + ":" + symbol + ":" + ",".join(codes)),
        analysis_id=analysis_id,
        symbol=symbol,
        status=status,
        strategy_key=policy.key,
        strategy_version=policy.version,
        reason_codes=codes,
        explanation="; ".join(codes) if codes else "No mandatory policy failures",
        evaluated_at=evaluated_at,
        market_snapshot_at=market_at,
        order_intent=intent,
    )


def _hash(body: dict) -> str:
    serialized = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _is_fresh(timestamp: datetime, now: datetime, max_age_seconds: int) -> bool:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return False
    seconds = (now.astimezone(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
    return -30 <= seconds <= max_age_seconds


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _time_string(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value and value.tzinfo else None


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))
