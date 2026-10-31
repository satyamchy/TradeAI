"""Pydantic contracts for analysis jobs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.shared.contracts import AnalysisStatus


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
