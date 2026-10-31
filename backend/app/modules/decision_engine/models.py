"""Decision and approved-intent persistence owned by Module 3."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import Base


class DecisionRecord(Base):
    __tablename__ = "trade_decisions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('BUY_APPROVED', 'HOLD', 'REJECTED', 'SELL_APPROVED', 'REVIEW_REQUIRED')",
            name="ck_trade_decisions_status",
        ),
        UniqueConstraint("decision_key", name="uq_trade_decisions_decision_key"),
        Index("ix_trade_decisions_owner_created", "owner_id", "created_at"),
    )

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_key: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrderIntentRecord(Base):
    __tablename__ = "approved_order_intents"
    __table_args__ = (
        UniqueConstraint("decision_id", name="uq_order_intents_decision"),
        UniqueConstraint("idempotency_key", name="uq_order_intents_idempotency"),
        CheckConstraint("status IN ('APPROVED', 'CONSUMED', 'EXPIRED')", name="ck_order_intents_status"),
    )

    order_intent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trade_decisions.decision_id", ondelete="RESTRICT"), nullable=False
    )
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    intent_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
