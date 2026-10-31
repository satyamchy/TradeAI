"""Versioned Pydantic contracts shared by business modules.

These models intentionally contain no provider, broker, ORM, or client types.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    """Base type for module boundary payloads."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SelectionMode(StrEnum):
    MANUAL = "MANUAL"
    TOP_GAINERS = "TOP_GAINERS"
    TOP_LOSERS = "TOP_LOSERS"
    MOMENTUM = "MOMENTUM"
    HIGH_VOLUME = "HIGH_VOLUME"


class AnalysisHorizon(StrEnum):
    INTRADAY = "INTRADAY"
    SWING = "SWING"
    RESEARCH = "RESEARCH"


class ProviderName(StrEnum):
    TRADING_AGENTS = "TRADING_AGENTS"
    LEGACY_LANGGRAPH = "LEGACY_LANGGRAPH"
    FUTURE_PROVIDER = "FUTURE_PROVIDER"


class AnalysisDirection(StrEnum):
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    REVIEW = "REVIEW"


class AnalysisStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DecisionStatus(StrEnum):
    BUY_APPROVED = "BUY_APPROVED"
    HOLD = "HOLD"
    REJECTED = "REJECTED"
    SELL_APPROVED = "SELL_APPROVED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class ExecutionMode(StrEnum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class PositionStatus(StrEnum):
    OPEN = "OPEN"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED = "CLOSED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class Instrument(Contract):
    symbol: str = Field(min_length=1, max_length=32)
    exchange: str = "NSE"
    trading_symbol: str | None = None
    analysis_ticker: str | None = None
    security_id: str | None = None
    segment: str | None = None
    currency: str = "INR"


class CreateCandidatesRequest(Contract):
    selection_mode: SelectionMode
    symbols: list[str] = Field(min_length=1)
    horizon: AnalysisHorizon
    exchange: str = "NSE"


class Candidate(Contract):
    candidate_id: UUID
    instrument: Instrument
    selection_mode: SelectionMode
    selection_reason: str
    validation_status: str


class CandidateBatch(Contract):
    batch_id: UUID
    status: str
    candidates: list[Candidate]
    rejected_symbols: list[str] = Field(default_factory=list)
    created_at: datetime


class AnalysisRequest(Contract):
    candidate_id: UUID
    provider: ProviderName
    analysis_date: date
    horizon: AnalysisHorizon
    analysis_profile_key: str
    analysis_profile_version: str
    selected_analysts: list[str] = Field(default_factory=list)
    include_portfolio_context: bool = False
    checkpoint_enabled: bool = False
    save_html_report: bool = True


class AnalysisJobReceipt(Contract):
    analysis_id: UUID
    candidate_id: UUID
    status: AnalysisStatus = AnalysisStatus.PENDING
    provider: ProviderName
    created_at: datetime


class AnalysisResult(Contract):
    analysis_id: UUID
    candidate_id: UUID
    symbol: str
    analysis_ticker: str
    provider: ProviderName
    provider_version: str
    profile_key: str
    profile_version: str
    status: AnalysisStatus
    source_rating: str | None = None
    direction: AnalysisDirection
    reports: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    report_artifacts: dict[str, Any] = Field(default_factory=dict)


class EvaluateTradeRequest(Contract):
    analysis_id: UUID
    strategy_key: str
    requested_action: str = "ENTRY"


class ApprovedOrderIntent(Contract):
    order_intent_id: UUID
    decision_id: UUID
    symbol: str
    security_id: str
    side: OrderSide
    quantity: int = Field(gt=0)
    order_type: OrderType
    limit_price: Decimal | None = None
    stop_loss: Decimal | None = None
    target: Decimal | None = None
    max_risk_amount: Decimal = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=128)
    expires_at: datetime | None = None


class DecisionResult(Contract):
    decision_id: UUID
    analysis_id: UUID
    symbol: str
    status: DecisionStatus
    strategy_key: str
    strategy_version: str
    reason_codes: list[str] = Field(default_factory=list)
    explanation: str
    market_snapshot_at: datetime | None = None
    order_intent: ApprovedOrderIntent | None = None


class ExecutionRequest(Contract):
    order_intent_id: UUID
    execution_mode: ExecutionMode


class ExecutionResult(Contract):
    tradeai_order_id: UUID
    order_intent_id: UUID
    broker: str
    broker_order_id: str | None = None
    status: OrderStatus
    requested_quantity: int = Field(gt=0)
    filled_quantity: int = Field(default=0, ge=0)
    remaining_quantity: int = Field(ge=0)
    average_fill_price: Decimal | None = None
    idempotency_key: str
    submitted_at: datetime
    updated_at: datetime


class PositionSnapshot(Contract):
    position_id: UUID
    symbol: str
    status: PositionStatus
    quantity: int
    average_price: Decimal
    current_price: Decimal | None = None
    market_data_at: datetime | None = None


class PositionEvaluation(Contract):
    position_id: UUID
    symbol: str
    status: PositionStatus
    action: str
    current_price: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    trigger_reason: str | None = None
    market_data_at: datetime | None = None
