"""Durable order lifecycle and reconciliation events owned by Module 4."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import Base


class ExecutionOrderRecord(Base):
    __tablename__ = "execution_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED', 'SUBMITTED', 'PENDING', 'OPEN', 'PARTIALLY_FILLED', "
            "'FILLED', 'REJECTED', 'CANCELLED', 'UNKNOWN')",
            name="ck_execution_orders_status",
        ),
        CheckConstraint("filled_quantity >= 0 AND remaining_quantity >= 0", name="ck_execution_orders_quantities"),
        UniqueConstraint("idempotency_key", name="uq_execution_orders_idempotency"),
        Index("ix_execution_orders_owner_status", "owner_id", "status"),
    )

    tradeai_order_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_intent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    broker: Mapped[str] = mapped_column(String(32), nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(String(128))
    execution_mode: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    requested_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remaining_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    average_fill_price: Mapped[str | None] = mapped_column(String(32))
    rejection_reason: Mapped[str | None] = mapped_column(String(256))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExecutionEventRecord(Base):
    __tablename__ = "execution_order_events"
    __table_args__ = (
        Index("ix_execution_order_events_order_time", "tradeai_order_id", "occurred_at"),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tradeai_order_id: Mapped[str] = mapped_column(
        ForeignKey("execution_orders.tradeai_order_id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
