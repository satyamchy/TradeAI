"""Deduplicated deterministic trigger audit records."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import Base


class PositionTriggerRecord(Base):
    __tablename__ = "position_monitor_triggers"
    __table_args__ = (
        UniqueConstraint("position_id", "trigger_key", name="uq_position_monitor_trigger"),
        CheckConstraint(
            "trigger_reason IN ('STOP_LOSS', 'TARGET_REACHED', 'SESSION_SQUARE_OFF')",
            name="ck_position_monitor_trigger_reason",
        ),
    )

    trigger_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    position_id: Mapped[str] = mapped_column(String(36), nullable=False)
    trigger_key: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger_reason: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_price: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)

