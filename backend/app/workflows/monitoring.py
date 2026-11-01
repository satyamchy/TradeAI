"""Cross-module flow from reconciled fills into deterministic monitoring."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.execution.service import ExecutionServiceProtocol
from app.modules.position_monitoring.schemas import (
    MarketObservation,
    MonitorRules,
    PositionMonitorInput,
)
from app.modules.position_monitoring.service import PositionMonitoringServiceProtocol
from app.shared.contracts import ApprovedOrderIntent, PositionEvaluation
from app.shared.identifiers import position_id_for
from app.shared.logging import bind_log_context, reset_log_context
from app.workflows.schemas import ConfirmedOpenPosition


class ApprovedIntentReader(Protocol):
    async def get_approved_intent(
        self, intent_id: UUID, *, owner_id: int
    ) -> ApprovedOrderIntent | None: ...


class ConfirmedPositionReader(Protocol):
    async def get_open_position(
        self,
        *,
        owner_id: int,
        symbol: str,
        security_id: str,
        product_type: str,
    ) -> ConfirmedOpenPosition | None: ...


class PositionNotReadyForMonitoring(ValueError):
    """No confirmed execution fill or approved intent is available to monitor."""


class ExecutionPositionWorkflow:
    """Feed Module 5 from confirmed broker position state after a reconciled fill."""

    def __init__(
        self,
        executions: ExecutionServiceProtocol,
        decisions: ApprovedIntentReader,
        monitoring: PositionMonitoringServiceProtocol,
        positions: ConfirmedPositionReader,
    ):
        self._executions = executions
        self._decisions = decisions
        self._monitoring = monitoring
        self._positions = positions

    async def evaluate_reconciled_execution(
        self,
        order_id: UUID,
        *,
        owner_id: int,
        market: MarketObservation,
        rules: MonitorRules,
    ) -> PositionEvaluation | None:
        execution = await self._executions.reconcile_order(order_id, owner_id=owner_id)
        intent = await self._decisions.get_approved_intent(execution.order_intent_id, owner_id=owner_id)
        if intent is None:
            raise PositionNotReadyForMonitoring("approved execution intent is unavailable")
        if execution.filled_quantity <= 0:
            raise PositionNotReadyForMonitoring("broker has not confirmed a fill")
        position = await self._positions.get_open_position(
            owner_id=owner_id,
            symbol=intent.symbol,
            security_id=intent.security_id,
            product_type=intent.product_type,
        )
        if position is None:
            return None

        position_id = intent.position_id or position_id_for(
            owner_id=owner_id,
            exchange=intent.exchange,
            symbol=intent.symbol,
            product_type=intent.product_type,
        )
        monitor_input = PositionMonitorInput(
            position_id=position_id,
            symbol=intent.symbol,
            confirmed_open_quantity=position.quantity,
            average_price=position.average_price,
            opened_at=position.opened_at,
            status=position.status,
            market=market,
            rules=rules,
        )
        tokens = bind_log_context(
            module="workflows",
            position_id=str(position_id),
            execution_order_id=str(execution.tradeai_order_id),
        )
        try:
            return self._monitoring.evaluate(monitor_input)
        finally:
            reset_log_context(tokens)


__all__ = ["ExecutionPositionWorkflow", "PositionNotReadyForMonitoring"]
