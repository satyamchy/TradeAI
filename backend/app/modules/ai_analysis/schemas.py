"""Versioned TradeX analysis profiles and provider adapter contracts."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator

from app.shared.contracts import (
    AnalysisDirection,
    AnalysisHorizon,
    AnalysisRequest,
    AnalysisResult,
    AnalysisStatus,
    Contract,
    Instrument,
)

SUPPORTED_TRADINGAGENTS_ANALYSTS = frozenset({"market", "social", "news", "fundamentals"})


class AnalysisProfile(Contract):
    """Immutable TradeX profile snapshot mapped to upstream config per run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=32)
    horizon: AnalysisHorizon
    selected_analysts: tuple[str, ...]
    quick_provider: str = Field(min_length=1, max_length=32)
    quick_model: str = Field(min_length=1, max_length=128)
    deep_provider: str = Field(min_length=1, max_length=32)
    deep_model: str = Field(min_length=1, max_length=128)
    max_debate_rounds: int = Field(default=1, ge=0, le=10)
    max_risk_discuss_rounds: int = Field(default=1, ge=0, le=10)
    checkpoint_enabled: bool = False
    save_html_report: bool = True
    portfolio_context_required: bool = False
    max_portfolio_age_seconds: int = Field(default=300, ge=1, le=86_400)

    @field_validator("selected_analysts")
    @classmethod
    def validate_selected_analysts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip().lower() for item in value)
        if not normalized:
            raise ValueError("at least one TradingAgents analyst must be selected")
        if len(set(normalized)) != len(normalized):
            raise ValueError("selected analysts must be unique")
        unsupported = set(normalized) - SUPPORTED_TRADINGAGENTS_ANALYSTS
        if unsupported:
            raise ValueError("unsupported TradingAgents analyst(s): " + ", ".join(sorted(unsupported)))
        return normalized


class PortfolioPosition(Contract):
    ticker: str = Field(min_length=1, max_length=64)
    quantity: Decimal
    average_price: Decimal | None = None


class PortfolioSnapshotReference(Contract):
    """Fresh, application-owned account context passed into a research run."""

    snapshot_id: UUID
    captured_at: datetime
    currency: str = Field(min_length=1, max_length=8)
    cash: Decimal | None = None
    positions: list[PortfolioPosition] = Field(default_factory=list)

    @field_validator("captured_at")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("portfolio snapshot timestamp must be timezone-aware")
        return value


class AnalysisProviderRequest(Contract):
    analysis_id: UUID
    candidate_id: UUID
    instrument: Instrument
    analysis_date: date
    horizon: AnalysisHorizon
    profile: AnalysisProfile
    portfolio: PortfolioSnapshotReference | None = None
    warnings: list[str] = Field(default_factory=list)


class AnalysisProviderOutput(Contract):
    """Safe provider output before its TradeX direction/result normalization."""

    provider_version: str
    source_rating: str | None = None
    reports: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    report_artifacts: dict[str, Any] = Field(default_factory=dict)


class AnalysisFilters(Contract):
    candidate_id: UUID | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = Field(default=50, ge=1, le=250)
    offset: int = Field(default=0, ge=0)


__all__ = [
    "AnalysisDirection",
    "AnalysisFilters",
    "AnalysisHorizon",
    "AnalysisProfile",
    "AnalysisProviderOutput",
    "AnalysisProviderRequest",
    "AnalysisRequest",
    "AnalysisResult",
    "AnalysisStatus",
    "PortfolioPosition",
    "PortfolioSnapshotReference",
]
