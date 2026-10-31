"""Synthetic and confirmed-position monitoring input contracts."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.shared.contracts import Contract, PositionEvaluation, PositionSnapshot, PositionStatus


class MarketObservation(Contract):
    price: Decimal | None = Field(default=None, gt=0)
    captured_at: datetime | None = None
    market_open: bool = False

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("market observation time must be timezone-aware")
        return value


class MonitorRules(Contract):
    version: str = Field(min_length=1, max_length=32)
    stop_loss_price: Decimal | None = Field(default=None, gt=0)
    target_price: Decimal | None = Field(default=None, gt=0)
    square_off_at: datetime | None = None
    max_market_age_seconds: int = Field(default=30, gt=0)

    @field_validator("square_off_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("square-off time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_price_rules(self) -> "MonitorRules":
        if self.stop_loss_price is not None and self.target_price is not None:
            if self.stop_loss_price >= self.target_price:
                raise ValueError("stop loss must be below the target for long positions")
        return self


class PositionMonitorInput(Contract):
    position_id: UUID
    symbol: str = Field(min_length=1, max_length=32)
    confirmed_open_quantity: int = Field(gt=0)
    average_price: Decimal = Field(gt=0)
    opened_at: datetime
    status: PositionStatus = PositionStatus.OPEN
    market: MarketObservation
    rules: MonitorRules

    @field_validator("opened_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("position open time must be timezone-aware")
        return value


__all__ = [
    "MarketObservation",
    "MonitorRules",
    "PositionEvaluation",
    "PositionMonitorInput",
    "PositionSnapshot",
    "PositionStatus",
]
