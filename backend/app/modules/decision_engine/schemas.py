"""Provider- and broker-neutral contracts owned by the decision engine."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.shared.contracts import (
    AnalysisResult,
    ApprovedOrderIntent,
    Contract,
    DecisionResult,
    DecisionStatus,
    EvaluateTradeRequest,
)


class MarketSnapshot(Contract):
    symbol: str = Field(min_length=1, max_length=32)
    price: Decimal = Field(gt=0)
    captured_at: datetime
    market_open: bool
    entries_allowed: bool = True

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("market snapshot timestamp must be timezone-aware")
        return value


class ConfirmedPosition(Contract):
    symbol: str
    security_id: str
    quantity: int = Field(gt=0)
    average_price: Decimal = Field(gt=0)
    market_value: Decimal = Field(ge=0)


class AccountRiskSnapshot(Contract):
    captured_at: datetime
    available_funds: Decimal = Field(ge=0)
    available_margin: Decimal | None = Field(default=None, ge=0)
    total_exposure: Decimal = Field(ge=0)
    daily_loss: Decimal = Field(ge=0)
    kill_switch_enabled: bool = False
    pending_symbols: list[str] = Field(default_factory=list)
    blocked_symbols: list[str] = Field(default_factory=list)
    confirmed_positions: list[ConfirmedPosition] = Field(default_factory=list)
    configured_limits: dict[str, Decimal | int] = Field(default_factory=dict)

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("account snapshot timestamp must be timezone-aware")
        return value


class StrategyPolicy(Contract):
    """Versioned, explicit initial long-only equity risk parameters."""

    key: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=32)
    max_market_age_seconds: int = Field(default=30, gt=0)
    max_account_age_seconds: int = Field(default=60, gt=0)
    max_analysis_age_seconds: int = Field(default=3600, gt=0)
    max_risk_amount: Decimal = Field(gt=0)
    risk_budget_fraction: Decimal = Field(gt=0, le=1)
    max_order_value: Decimal = Field(gt=0)
    max_symbol_exposure: Decimal = Field(gt=0)
    max_total_exposure: Decimal = Field(gt=0)
    max_daily_loss: Decimal = Field(gt=0)
    stop_loss_pct: Decimal = Field(gt=0, lt=100)
    target_pct: Decimal = Field(gt=0)
    max_positions: int = Field(default=4, gt=0)
    intent_ttl_seconds: int = Field(default=30, gt=0)
    order_type: str = "MARKET"
    product_type: str = "INTRADAY"

    @model_validator(mode="after")
    def validate_order_options(self) -> "StrategyPolicy":
        if self.order_type not in {"MARKET", "LIMIT"}:
            raise ValueError("order_type must be MARKET or LIMIT")
        if self.product_type not in {"INTRADAY", "DELIVERY"}:
            raise ValueError("product_type must be INTRADAY or DELIVERY")
        return self


class ExitEvaluationRequest(Contract):
    """Deterministic exit request from a confirmed position or monitor rule."""

    position_id: UUID
    symbol: str = Field(min_length=1, max_length=32)
    security_id: str = Field(min_length=1, max_length=64)
    confirmed_open_quantity: int = Field(gt=0)
    requested_quantity: int | None = Field(default=None, gt=0)
    average_price: Decimal = Field(gt=0)
    strategy_key: str = Field(min_length=1, max_length=64)
    strategy_version: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=1, max_length=256)


class DecisionEvaluationContext(Contract):
    analysis: AnalysisResult
    market: MarketSnapshot
    account: AccountRiskSnapshot
    policy: StrategyPolicy
    evaluated_at: datetime
    security_id: str | None = None
    exchange: str = "NSE"
    segment: str = "NSE_EQ"

    @field_validator("evaluated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("decision time must be timezone-aware")
        return value


__all__ = [
    "AccountRiskSnapshot",
    "ApprovedOrderIntent",
    "ConfirmedPosition",
    "DecisionEvaluationContext",
    "DecisionResult",
    "DecisionStatus",
    "EvaluateTradeRequest",
    "ExitEvaluationRequest",
    "MarketSnapshot",
    "StrategyPolicy",
]
