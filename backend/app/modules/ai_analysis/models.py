"""Module-owned persistence for normalized provider analysis results."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import Base


class AnalysisRunRecord(Base):
    """One immutable configuration snapshot and its normalized result."""

    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_analysis_runs_status",
        ),
        Index("ix_analysis_runs_candidate_created_at", "candidate_id", "created_at"),
    )

    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_jobs.analysis_id", ondelete="CASCADE"), primary_key=True
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stock_candidates.candidate_id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(32), nullable=False)
    profile_key: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    run_config_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
