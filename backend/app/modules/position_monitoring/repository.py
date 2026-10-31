"""Persistent deduplication for monitoring trigger candidates."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.modules.position_monitoring.models import PositionTriggerRecord


class TriggerRepository(Protocol):
    def record_trigger(
        self, *, position_id: UUID, reason: str, policy_version: str,
        price: Decimal | None, occurred_at: datetime,
    ) -> tuple[UUID, bool]: ...


class SqlAlchemyTriggerRepository:
    def __init__(self, sessions: sessionmaker):
        self._sessions = sessions

    def record_trigger(
        self, *, position_id: UUID, reason: str, policy_version: str,
        price: Decimal | None, occurred_at: datetime,
    ) -> tuple[UUID, bool]:
        trigger_key = f"{reason}:{policy_version}"
        with self._sessions() as session:
            existing = session.scalar(select(PositionTriggerRecord).where(
                PositionTriggerRecord.position_id == str(position_id),
                PositionTriggerRecord.trigger_key == trigger_key,
            ))
            if existing:
                return UUID(existing.trigger_id), False
            record = PositionTriggerRecord(
                trigger_id=str(uuid4()),
                position_id=str(position_id),
                trigger_key=trigger_key,
                trigger_reason=reason,
                policy_version=policy_version,
                trigger_price=str(price) if price is not None else None,
                created_at=occurred_at,
                detail=json.dumps({"reason": reason, "policy_version": policy_version}, separators=(",", ":")),
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(select(PositionTriggerRecord).where(
                    PositionTriggerRecord.position_id == str(position_id),
                    PositionTriggerRecord.trigger_key == trigger_key,
                ))
                if existing is None:
                    raise
                return UUID(existing.trigger_id), False
            return UUID(record.trigger_id), True

