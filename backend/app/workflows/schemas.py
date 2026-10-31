"""Typed results for cross-module workflow outcomes."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator

from app.shared.contracts import (
    Contract,
    DecisionResult,
    ExecutionResult,
    PositionStatus,
)


class ConfirmedOpenPosition(Contract):
    """Broker- or paper-ledger-confirmed open position snapshot."""

    quantity: int = Field(gt=0)
    average_price: Decimal = Field(gt=0)
    opened_at: datetime
    status: PositionStatus = PositionStatus.OPEN

    @field_validator("opened_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("position open time must be timezone-aware")
        return value


class PositionExitOutcome(Contract):
    trigger_id: UUID
    deduplicated: bool = False
    decision: DecisionResult | None = None
    execution: ExecutionResult | None = None


__all__ = ["ConfirmedOpenPosition", "PositionExitOutcome"]
