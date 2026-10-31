"""Fail-safe orchestration for deduplicated deterministic exit candidates."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.modules.decision_engine.schemas import ExitEvaluationRequest
from app.modules.execution.schemas import ExecutionResult
from app.modules.position_monitoring.schemas import PositionEvaluation
from app.shared.contracts import DecisionResult, DecisionStatus, ExecutionMode
from app.shared.logging import bind_log_context, reset_log_context
from app.workflows.schemas import PositionExitOutcome


class InvalidExitCandidate(ValueError):
    """Exit trigger is incomplete or exceeds the caller's confirmed position."""


class ExitDecisionService(Protocol):
    async def evaluate_exit(self, request: ExitEvaluationRequest, *, owner_id: int) -> DecisionResult: ...


class DecisionExecutionPort(Protocol):
    async def execute_decision(
        self, decision_id: UUID, *, owner_id: int, mode: ExecutionMode
    ) -> ExecutionResult: ...


class PositionExitWorkflow:
    """Route a new deterministic monitor trigger through Module 3 and Module 4."""

    def __init__(self, decisions: ExitDecisionService, executions: DecisionExecutionPort):
        self._decisions = decisions
        self._executions = executions

    async def process_exit_candidate(
        self,
        evaluation: PositionEvaluation,
        *,
        owner_id: int,
        security_id: str,
        confirmed_open_quantity: int,
        average_price: Decimal,
        strategy_key: str,
        strategy_version: str,
        mode: ExecutionMode,
    ) -> PositionExitOutcome:
        if evaluation.action != "EXIT_CANDIDATE" or evaluation.trigger_id is None:
            raise InvalidExitCandidate("a persisted monitoring exit trigger is required")
        if not evaluation.is_new_trigger:
            return PositionExitOutcome(trigger_id=evaluation.trigger_id, deduplicated=True)
        if not security_id or confirmed_open_quantity <= 0 or average_price <= 0:
            raise InvalidExitCandidate("confirmed security and open-position details are required")
        quantity = evaluation.exit_quantity
        if quantity is None or quantity <= 0 or quantity > confirmed_open_quantity:
            raise InvalidExitCandidate("monitor exit quantity exceeds the confirmed open quantity")
        if not evaluation.trigger_reason:
            raise InvalidExitCandidate("monitor exit reason is required")

        tokens = bind_log_context(
            module="workflows",
            position_id=str(evaluation.position_id),
            decision_trigger_id=str(evaluation.trigger_id),
        )
        try:
            decision = await self._decisions.evaluate_exit(
                ExitEvaluationRequest(
                    position_id=evaluation.position_id,
                    symbol=evaluation.symbol,
                    security_id=security_id,
                    confirmed_open_quantity=confirmed_open_quantity,
                    requested_quantity=quantity,
                    average_price=average_price,
                    strategy_key=strategy_key,
                    strategy_version=strategy_version,
                    reason=evaluation.trigger_reason,
                ),
                owner_id=owner_id,
            )
            execution = None
            if decision.status is DecisionStatus.SELL_APPROVED:
                if decision.order_intent is None:
                    raise InvalidExitCandidate("Module 3 approved an exit without a persisted intent")
                execution = await self._executions.execute_decision(
                    decision.decision_id,
                    owner_id=owner_id,
                    mode=mode,
                )
            return PositionExitOutcome(
                trigger_id=evaluation.trigger_id,
                decision=decision,
                execution=execution,
            )
        finally:
            reset_log_context(tokens)


__all__ = ["InvalidExitCandidate", "PositionExitWorkflow"]
