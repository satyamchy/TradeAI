"""Idempotent broker execution and reconciliation over injected adapters."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from app.modules.execution.repository import ExecutionRepository
from app.modules.execution.schemas import BrokerOrderUpdate, ReconciliationSummary
from app.shared.contracts import (
    ApprovedOrderIntent,
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    OrderStatus,
)


class ApprovedIntentLookup(Protocol):
    async def get_approved_intent(self, intent_id: UUID, *, owner_id: int) -> ApprovedOrderIntent | None: ...


class BrokerAdapter(Protocol):
    name: str

    async def submit(self, intent: ApprovedOrderIntent, *, mode: ExecutionMode) -> BrokerOrderUpdate: ...
    async def get_order_status(self, order: ExecutionResult) -> BrokerOrderUpdate: ...
    async def cancel_order(self, order: ExecutionResult) -> BrokerOrderUpdate: ...


class ExecutionServiceProtocol(Protocol):
    async def execute_order(self, request: ExecutionRequest, *, owner_id: int) -> ExecutionResult: ...
    async def get_order_status(self, order_id: UUID, *, owner_id: int) -> ExecutionResult | None: ...
    async def cancel_order(self, order_id: UUID, *, owner_id: int) -> ExecutionResult: ...
    async def reconcile_order(self, order_id: UUID, *, owner_id: int) -> ExecutionResult: ...
    async def reconcile_orders(self, *, owner_id: int) -> ReconciliationSummary: ...


class ExecutionError(RuntimeError):
    """Base error for rejected execution requests."""


class IntentUnavailable(ExecutionError):
    """The owner does not have an approved persisted intent with this ID."""


class InvalidExecutionRequest(ExecutionError):
    """The persisted intent is invalid, expired, or the mode is not allowed."""


class LiveExecutionDisabled(InvalidExecutionRequest):
    """Live order requests are blocked by the application master gate."""


class IdempotencyConflict(ExecutionError):
    """A key is already bound to a different persisted intent."""


class ExecutionService:
    """Only submits persisted approved intents and never blind-retries unknowns."""

    def __init__(
        self,
        *,
        intents: ApprovedIntentLookup,
        repository: ExecutionRepository,
        broker: BrokerAdapter,
        live_execution_allowed: bool = False,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self._intents = intents
        self._repository = repository
        self._broker = broker
        self._live_execution_allowed = live_execution_allowed
        self._clock = clock

    async def execute_order(self, request: ExecutionRequest, *, owner_id: int) -> ExecutionResult:
        intent = await self._intents.get_approved_intent(request.order_intent_id, owner_id=owner_id)
        if intent is None:
            raise IntentUnavailable("Approved order intent was not found")
        now = _aware(self._clock())
        _validate_intent(intent, request, now, self._live_execution_allowed)

        existing = self._repository.get_by_idempotency(intent.idempotency_key, owner_id=owner_id)
        if existing is not None:
            if existing.order_intent_id != intent.order_intent_id:
                raise IdempotencyConflict("Idempotency key is already associated with a different intent")
            return existing

        order_id = uuid4()
        reserved = ExecutionResult(
            tradeai_order_id=order_id,
            order_intent_id=intent.order_intent_id,
            broker=self._broker.name,
            broker_order_id=None,
            status=OrderStatus.PENDING,
            requested_quantity=intent.quantity,
            filled_quantity=0,
            remaining_quantity=intent.quantity,
            idempotency_key=intent.idempotency_key,
            submitted_at=now,
            updated_at=now,
            execution_mode=request.execution_mode,
        )
        current, created = self._repository.reserve(reserved, owner_id=owner_id)
        if not created:
            if current.order_intent_id != intent.order_intent_id:
                raise IdempotencyConflict("Idempotency key is already associated with a different intent")
            return current

        try:
            update = await self._broker.submit(intent, mode=request.execution_mode)
            return self._apply_broker_update(current, update, owner_id)
        except Exception:
            # The broker may have accepted the request before the connection failed.
            # Keep the idempotency reservation and require reconciliation before retry.
            unknown = current.model_copy(update={
                "status": OrderStatus.UNKNOWN,
                "updated_at": _aware(self._clock()),
                "rejection_reason": "SUBMISSION_OUTCOME_UNKNOWN",
            })
            return self._repository.update(unknown, owner_id=owner_id, detail="SUBMISSION_OUTCOME_UNKNOWN")

    async def get_order_status(self, order_id: UUID, *, owner_id: int) -> ExecutionResult | None:
        return self._repository.get(order_id, owner_id=owner_id)

    async def list_orders(self, *, owner_id: int) -> list[ExecutionResult]:
        return self._repository.list_for_owner(owner_id=owner_id)

    async def cancel_order(self, order_id: UUID, *, owner_id: int) -> ExecutionResult:
        order = self._repository.get(order_id, owner_id=owner_id)
        if order is None:
            raise LookupError("execution order not found")
        if order.status not in {OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED, OrderStatus.UNKNOWN}:
            return order
        try:
            update = await self._broker.cancel_order(order)
            return self._apply_broker_update(order, update, owner_id)
        except Exception:
            return self._repository.update(
                order.model_copy(update={
                    "status": OrderStatus.UNKNOWN,
                    "updated_at": _aware(self._clock()),
                    "rejection_reason": "CANCEL_OUTCOME_UNKNOWN",
                }),
                owner_id=owner_id,
                detail="CANCEL_OUTCOME_UNKNOWN",
            )

    async def reconcile_order(self, order_id: UUID, *, owner_id: int) -> ExecutionResult:
        order = self._repository.get(order_id, owner_id=owner_id)
        if order is None:
            raise LookupError("execution order not found")
        if order.status in {OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED}:
            return order
        try:
            update = await self._broker.get_order_status(order)
            return self._apply_broker_update(order, update, owner_id)
        except Exception:
            unknown = order.model_copy(update={
                "status": OrderStatus.UNKNOWN,
                "updated_at": _aware(self._clock()),
                "rejection_reason": "RECONCILIATION_UNAVAILABLE",
            })
            return self._repository.update(unknown, owner_id=owner_id, detail="RECONCILIATION_UNAVAILABLE")

    async def reconcile_orders(self, *, owner_id: int) -> ReconciliationSummary:
        pending = self._repository.list_reconcilable(owner_id=owner_id)
        updated: list[ExecutionResult] = []
        for order in pending:
            updated.append(await self.reconcile_order(order.tradeai_order_id, owner_id=owner_id))
        return ReconciliationSummary(
            checked=len(pending),
            updated=sum(left != right for left, right in zip(pending, updated)),
            unknown=sum(order.status is OrderStatus.UNKNOWN for order in updated),
            order_ids=[order.tradeai_order_id for order in updated],
        )

    def _apply_broker_update(
        self, order: ExecutionResult, update: BrokerOrderUpdate, owner_id: int
    ) -> ExecutionResult:
        if update.filled_quantity > order.requested_quantity:
            result = order.model_copy(update={
                "status": OrderStatus.UNKNOWN,
                "updated_at": _aware(self._clock()),
                "rejection_reason": "BROKER_UPDATE_INVALID_QUANTITY",
            })
            return self._repository.update(result, owner_id=owner_id, detail="BROKER_UPDATE_INVALID_QUANTITY")
        status = _normalize_status(update.status, update.filled_quantity, order.requested_quantity)
        remaining = order.requested_quantity - update.filled_quantity
        rejection_reason = _safe_reason(update.rejection_reason) if status is OrderStatus.REJECTED else None
        result = order.model_copy(update={
            "broker": update.broker,
            "broker_order_id": update.broker_order_id or order.broker_order_id,
            "status": status,
            "filled_quantity": update.filled_quantity,
            "remaining_quantity": remaining,
            "average_fill_price": update.average_fill_price,
            "updated_at": _aware(update.updated_at),
            "rejection_reason": rejection_reason,
        })
        return self._repository.update(result, owner_id=owner_id, detail="BROKER_STATUS_RECONCILED")


def _validate_intent(
    intent: ApprovedOrderIntent,
    request: ExecutionRequest,
    now: datetime,
    live_execution_allowed: bool,
) -> None:
    if intent.order_intent_id != request.order_intent_id:
        raise IntentUnavailable("Intent ID mismatch")
    if not intent.idempotency_key.strip() or intent.quantity <= 0 or not intent.security_id.strip():
        raise InvalidExecutionRequest("Persisted intent is missing mandatory execution fields")
    if intent.reference_price is None and intent.limit_price is None:
        raise InvalidExecutionRequest("Persisted intent has no reference or limit price")
    if intent.expires_at is None or _aware(intent.expires_at) <= now:
        raise InvalidExecutionRequest("Persisted order intent is expired")
    if intent.intent_kind not in {"ENTRY", "EXIT"}:
        raise InvalidExecutionRequest("Persisted order intent kind is invalid")
    order_type = getattr(intent.order_type, "value", intent.order_type)
    if order_type != "MARKET":
        raise InvalidExecutionRequest("The current single gateway path supports market orders only")
    if intent.exchange.upper() != "NSE" or (intent.segment and intent.segment.upper() != "NSE_EQ"):
        raise InvalidExecutionRequest("The current gateway path supports NSE equity instruments only")
    if request.execution_mode is ExecutionMode.LIVE and not live_execution_allowed:
        raise LiveExecutionDisabled("LIVE_TRADING_ENABLED and production live-mode checks are required")


def _normalize_status(raw_status: str, filled: int, requested: int) -> OrderStatus:
    value = raw_status.strip().upper().replace(" ", "_")
    if filled == requested:
        return OrderStatus.FILLED
    if filled > 0 and value not in {"REJECTED", "CANCELLED", "CANCELED", "EXPIRED"}:
        return OrderStatus.PARTIALLY_FILLED
    if value in {"REJECTED", "FAILED"}:
        return OrderStatus.REJECTED
    if value in {"CANCELLED", "CANCELED", "EXPIRED"}:
        return OrderStatus.CANCELLED
    if value in {"OPEN"}:
        return OrderStatus.OPEN
    if value in {"PENDING", "TRANSIT", "SUBMITTED", "ACCEPTED", "SUCCESS"}:
        return OrderStatus.PENDING
    if value in {"PART_TRADED", "PARTIALLY_FILLED"} and filled > 0:
        return OrderStatus.PARTIALLY_FILLED
    return OrderStatus.UNKNOWN


def _safe_reason(value: str | None) -> str | None:
    if not value:
        return "BROKER_REJECTED"
    cleaned = re.sub(r"(?i)(access[_ -]?token|api[_ -]?key|client[_ -]?secret|password)\s*[:=]\s*\S+", r"\1=[redacted]", value)
    return cleaned[:256]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
