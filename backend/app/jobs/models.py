"""SQLAlchemy representation of the single additive Phase 1 job table."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import Base


class AnalysisJobRecord(Base):
    """One durable request, uniquely scoped by user and idempotency key."""

    __tablename__ = "analysis_jobs"
    __table_args__ = (
        UniqueConstraint("created_by_user_id", "idempotency_key", name="uq_analysis_jobs_owner_idempotency"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_analysis_jobs_status",
        ),
        CheckConstraint("attempt_count >= 0 AND max_attempts >= 1", name="ck_analysis_jobs_attempts"),
        Index("ix_analysis_jobs_status_created_at", "status", "created_at"),
    )

    analysis_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # The migration owns the actual foreign-key constraint to the legacy users table.
    # That table is still served through sqlite3 and isn't mapped in this ORM metadata.
    created_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_reference: Mapped[str | None] = mapped_column(String(500))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    failure_message: Mapped[str | None] = mapped_column(String(500))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
