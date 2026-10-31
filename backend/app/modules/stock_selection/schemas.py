"""Public and internal typed schemas for Stock Selection."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.shared.contracts import (
    Candidate,
    CandidateBatch,
    CandidateRejection,
    CandidateRejectionCode,
    CandidateValidationStatus,
    Contract,
    CreateCandidatesRequest,
    Instrument,
)


class CandidateFilters(Contract):
    """Bounded filters for a user's candidate history."""

    exchange: str | None = None
    selection_mode: Literal["MANUAL"] | None = None
    horizon: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class InstrumentResolution(Contract):
    instrument: Instrument
    mapping_source: str = Field(min_length=1, max_length=64)
    resolved_at: datetime


class RankCandidatesRequest(Contract):
    """Input used to adapt the existing read-only index screener."""

    side: Literal["long", "short"]
    index: str = "NIFTY 50"
    limit: int = Field(default=6, ge=1, le=50)


class RankedCandidate(Contract):
    """Typed projection of the established screener response row."""

    symbol: str
    ltp: float = 0.0
    percent_change: float = 0.0
    score: float = 0.0
    volume_ratio: float | None = None
    rsi: float | None = None
    atr_percent: float | None = None
    vwap_deviation_percent: float | None = None


__all__ = [
    "Candidate",
    "CandidateBatch",
    "CandidateFilters",
    "CandidateRejection",
    "CandidateRejectionCode",
    "CandidateValidationStatus",
    "CreateCandidatesRequest",
    "Instrument",
    "InstrumentResolution",
    "RankCandidatesRequest",
    "RankedCandidate",
]
