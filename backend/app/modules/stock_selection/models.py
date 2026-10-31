"""SQLAlchemy persistence owned by Stock Selection."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import Base


class CandidateBatchRecord(Base):
    """Audit record for one manual selection request, including rejections."""

    __tablename__ = "candidate_batches"
    __table_args__ = (
        CheckConstraint("selection_mode IN ('MANUAL')", name="ck_candidate_batches_selection_mode"),
        CheckConstraint(
            "status IN ('COMPLETED', 'PARTIAL', 'REJECTED')",
            name="ck_candidate_batches_status",
        ),
        Index("ix_candidate_batches_owner_created_at", "created_by_user_id", "created_at"),
    )

    batch_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # The legacy users table is not represented in SQLAlchemy metadata yet.
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selection_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    horizon: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    submitted_symbols_json: Mapped[str] = mapped_column(Text, nullable=False)
    rejected_symbols_json: Mapped[str] = mapped_column(Text, nullable=False)
    rejections_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StockCandidateRecord(Base):
    """One validated candidate and its reproducible instrument mapping."""

    __tablename__ = "stock_candidates"
    __table_args__ = (
        CheckConstraint("selection_mode IN ('MANUAL')", name="ck_stock_candidates_selection_mode"),
        CheckConstraint(
            "validation_status IN ('VALID', 'ANALYSIS_ONLY')",
            name="ck_stock_candidates_validation_status",
        ),
        UniqueConstraint("batch_id", "symbol", name="uq_stock_candidates_batch_symbol"),
        Index("ix_stock_candidates_batch_id", "batch_id"),
        Index("ix_stock_candidates_symbol_exchange", "symbol", "exchange"),
    )

    candidate_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidate_batches.batch_id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    trading_symbol: Mapped[str | None] = mapped_column(String(32))
    analysis_ticker: Mapped[str | None] = mapped_column(String(64))
    security_id: Mapped[str | None] = mapped_column(String(64))
    segment: Mapped[str | None] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    selection_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    selection_reason: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    mapping_source: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
