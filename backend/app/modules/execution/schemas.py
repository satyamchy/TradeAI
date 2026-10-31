"""Broker adapter and normalized execution contracts."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator

from app.shared.contracts import (
    ApprovedOrderIntent,
    Contract,
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    OrderStatus,
)


class BrokerOrderUpdate(Contract):
    broker: str = Field(min_length=1, max_length=32)
    status: str = Field(min_length=1, max_length=32)
    broker_order_id: str | None = Field(default=None, max_length=128)
    filled_quantity: int = Field(default=0, ge=0)
    average_fill_price: Decimal | None = Field(default=None, gt=0)
    updated_at: datetime
    rejection_reason: str | None = Field(default=None, max_length=512)

    @field_validator("updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("broker timestamp must be timezone-aware")
        return value


class ReconciliationSummary(Contract):
    checked: int = Field(ge=0)
    updated: int = Field(ge=0)
    unknown: int = Field(ge=0)
    order_ids: list[UUID] = Field(default_factory=list)


class ExecutionEvent(Contract):
    event_id: UUID
    tradeai_order_id: UUID
    status: OrderStatus
    filled_quantity: int = Field(ge=0)
    remaining_quantity: int = Field(ge=0)
    occurred_at: datetime


__all__ = [
    "ApprovedOrderIntent",
    "BrokerOrderUpdate",
    "ExecutionEvent",
    "ExecutionMode",
    "ExecutionRequest",
    "ExecutionResult",
    "OrderStatus",
    "ReconciliationSummary",
]
