"""SQLAlchemy persistence for idempotent execution and status history."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.modules.execution.models import ExecutionEventRecord, ExecutionOrderRecord
from app.shared.contracts import ExecutionMode, ExecutionResult, OrderStatus


class ExecutionRepository(Protocol):
    def reserve(self, result: ExecutionResult, *, owner_id: int) -> tuple[ExecutionResult, bool]: ...
    def update(self, result: ExecutionResult, *, owner_id: int, detail: str | None = None) -> ExecutionResult: ...
    def get(self, order_id: UUID, *, owner_id: int) -> ExecutionResult | None: ...
    def get_by_idempotency(self, key: str, *, owner_id: int) -> ExecutionResult | None: ...
    def list_reconcilable(self, *, owner_id: int) -> list[ExecutionResult]: ...


class SqlAlchemyExecutionRepository:
    def __init__(self, sessions: sessionmaker):
        self._sessions = sessions

    def reserve(self, result: ExecutionResult, *, owner_id: int) -> tuple[ExecutionResult, bool]:
        with self._sessions() as session:
            existing = session.scalar(select(ExecutionOrderRecord).where(
                ExecutionOrderRecord.idempotency_key == result.idempotency_key,
                ExecutionOrderRecord.owner_id == owner_id,
            ))
            if existing:
                return _to_result(existing), False
            record = _to_record(result, owner_id)
            session.add(record)
            session.flush()
            session.add(_event(result, "SUBMISSION_RESERVED"))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(select(ExecutionOrderRecord).where(
                    ExecutionOrderRecord.idempotency_key == result.idempotency_key,
                    ExecutionOrderRecord.owner_id == owner_id,
                ))
                if existing is None:
                    raise
                return _to_result(existing), False
            return result, True

    def update(self, result: ExecutionResult, *, owner_id: int, detail: str | None = None) -> ExecutionResult:
        with self._sessions() as session:
            record = session.scalar(select(ExecutionOrderRecord).where(
                ExecutionOrderRecord.tradeai_order_id == str(result.tradeai_order_id),
                ExecutionOrderRecord.owner_id == owner_id,
            ))
            if record is None:
                raise LookupError("execution order not found")
            _assign(record, result)
            session.add(_event(result, detail))
            session.commit()
        return result

    def get(self, order_id: UUID, *, owner_id: int) -> ExecutionResult | None:
        with self._sessions() as session:
            record = session.scalar(select(ExecutionOrderRecord).where(
                ExecutionOrderRecord.tradeai_order_id == str(order_id),
                ExecutionOrderRecord.owner_id == owner_id,
            ))
            return _to_result(record) if record else None

    def get_by_idempotency(self, key: str, *, owner_id: int) -> ExecutionResult | None:
        with self._sessions() as session:
            record = session.scalar(select(ExecutionOrderRecord).where(
                ExecutionOrderRecord.idempotency_key == key,
                ExecutionOrderRecord.owner_id == owner_id,
            ))
            return _to_result(record) if record else None

    def list_reconcilable(self, *, owner_id: int) -> list[ExecutionResult]:
        statuses = ["PENDING", "OPEN", "PARTIALLY_FILLED", "UNKNOWN"]
        with self._sessions() as session:
            rows = session.scalars(select(ExecutionOrderRecord).where(
                ExecutionOrderRecord.owner_id == owner_id,
                ExecutionOrderRecord.status.in_(statuses),
            ).order_by(ExecutionOrderRecord.submitted_at)).all()
            return [_to_result(row) for row in rows]


def _to_record(result: ExecutionResult, owner_id: int) -> ExecutionOrderRecord:
    return ExecutionOrderRecord(
        tradeai_order_id=str(result.tradeai_order_id),
        order_intent_id=str(result.order_intent_id),
        owner_id=owner_id,
        idempotency_key=result.idempotency_key,
        broker=result.broker,
        broker_order_id=result.broker_order_id,
        execution_mode=result.execution_mode.value,
        status=result.status.value,
        requested_quantity=result.requested_quantity,
        filled_quantity=result.filled_quantity,
        remaining_quantity=result.remaining_quantity,
        average_fill_price=str(result.average_fill_price) if result.average_fill_price is not None else None,
        rejection_reason=result.rejection_reason,
        submitted_at=result.submitted_at,
        updated_at=result.updated_at,
    )


def _assign(record: ExecutionOrderRecord, result: ExecutionResult) -> None:
    record.broker = result.broker
    record.broker_order_id = result.broker_order_id
    record.status = result.status.value
    record.filled_quantity = result.filled_quantity
    record.remaining_quantity = result.remaining_quantity
    record.average_fill_price = str(result.average_fill_price) if result.average_fill_price is not None else None
    record.rejection_reason = result.rejection_reason
    record.updated_at = result.updated_at


def _to_result(record: ExecutionOrderRecord) -> ExecutionResult:
    from decimal import Decimal

    return ExecutionResult(
        tradeai_order_id=UUID(record.tradeai_order_id),
        order_intent_id=UUID(record.order_intent_id),
        broker=record.broker,
        broker_order_id=record.broker_order_id,
        status=OrderStatus(record.status),
        requested_quantity=record.requested_quantity,
        filled_quantity=record.filled_quantity,
        remaining_quantity=record.remaining_quantity,
        average_fill_price=Decimal(record.average_fill_price) if record.average_fill_price else None,
        idempotency_key=record.idempotency_key,
        submitted_at=_aware(record.submitted_at),
        updated_at=_aware(record.updated_at),
        execution_mode=ExecutionMode(record.execution_mode),
        rejection_reason=record.rejection_reason,
    )


def _event(result: ExecutionResult, detail: str | None) -> ExecutionEventRecord:
    return ExecutionEventRecord(
        event_id=str(uuid4()),
        tradeai_order_id=str(result.tradeai_order_id),
        status=result.status.value,
        filled_quantity=result.filled_quantity,
        remaining_quantity=result.remaining_quantity,
        detail=detail[:256] if detail else None,
        occurred_at=result.updated_at,
    )


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
