"""Pydantic contracts for analysis jobs."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.shared.contracts import AnalysisStatus


class AnalysisJobSubmission(BaseModel):
    """Sanitized request data and a caller-generated idempotency key."""

    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=128)
    request_payload: dict[str, Any] = Field(default_factory=dict)


class AnalysisJobView(BaseModel):
    """Safe job fields returned by the manager/API."""

    model_config = ConfigDict(from_attributes=True)

    analysis_id: UUID
    idempotency_key: str
    status: AnalysisStatus
    attempt_count: int
    max_attempts: int
    retryable: bool
    result_reference: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AnalysisJobHandlerResult(BaseModel):
    """Handler output is reduced to a reference, not a provider payload."""

    result_reference: str = Field(min_length=1, max_length=500)
