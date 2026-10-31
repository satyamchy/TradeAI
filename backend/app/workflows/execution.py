"""Cross-module orchestration from approved decisions to broker execution."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.decision_engine.schemas import DecisionResult
from app.modules.execution.schemas import ExecutionResult
from app.modules.execution.service import ExecutionServiceProtocol
from app.shared.contracts import DecisionStatus, ExecutionMode, ExecutionRequest
from app.shared.logging import bind_log_context, reset_log_context


class DecisionNotExecutable(ValueError):
    """Decision is missing, rejected, or has no Module 3 approved intent."""


class ApprovedDecisionLookup(Protocol):
    async def get_decision(self, decision_id: UUID, *, owner_id: int) -> DecisionResult | None: ...


class DecisionExecutionWorkflow:
    """Only pass persisted Module 3 approval to Module 4 for revalidation."""

    def __init__(self, decisions: ApprovedDecisionLookup, executions: ExecutionServiceProtocol):
        self._decisions = decisions
        self._executions = executions

    async def execute_decision(
        self,
        decision_id: UUID,
        *,
        owner_id: int,
        mode: ExecutionMode,
    ) -> ExecutionResult:
        decision = await self._decisions.get_decision(decision_id, owner_id=owner_id)
        if decision is None:
            raise DecisionNotExecutable("persisted decision was not found")
        if decision.status not in {DecisionStatus.BUY_APPROVED, DecisionStatus.SELL_APPROVED}:
            raise DecisionNotExecutable("decision is not approved for execution")
        intent = decision.order_intent
        if intent is None or intent.decision_id != decision.decision_id:
            raise DecisionNotExecutable("approved decision has no matching persisted order intent")

        tokens = bind_log_context(
            module="workflows",
            decision_id=str(decision_id),
        )
        try:
            return await self._executions.execute_order(
                ExecutionRequest(order_intent_id=intent.order_intent_id, execution_mode=mode),
                owner_id=owner_id,
            )
        finally:
            reset_log_context(tokens)

    async def reconcile_order(self, order_id: UUID, *, owner_id: int) -> ExecutionResult:
        tokens = bind_log_context(module="workflows", order_id=str(order_id))
        try:
            return await self._executions.reconcile_order(order_id, owner_id=owner_id)
        finally:
            reset_log_context(tokens)


__all__ = ["DecisionExecutionWorkflow", "DecisionNotExecutable"]
