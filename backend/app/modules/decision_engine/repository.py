"""SQLAlchemy repository for decisions and immutable approved intents."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.modules.decision_engine.models import DecisionRecord, OrderIntentRecord
from app.modules.decision_engine.schemas import DecisionResult
from app.shared.contracts import ApprovedOrderIntent


class DecisionRepository(Protocol):
    def save(self, result: DecisionResult, *, owner_id: int, decision_key: str) -> DecisionResult: ...
    def get(self, decision_id: UUID, *, owner_id: int) -> DecisionResult | None: ...
    def get_for_analysis(self, analysis_id: UUID, *, owner_id: int) -> DecisionResult | None: ...
    def list_for_owner(self, *, owner_id: int, analysis_id: UUID | None = None) -> list[DecisionResult]: ...
    def get_approved_intent(self, intent_id: UUID, *, owner_id: int) -> ApprovedOrderIntent | None: ...


class SqlAlchemyDecisionRepository:
    def __init__(self, sessions: sessionmaker):
        self._sessions = sessions

    def save(self, result: DecisionResult, *, owner_id: int, decision_key: str) -> DecisionResult:
        with self._sessions() as session:
            existing = session.scalar(
                select(DecisionRecord).where(DecisionRecord.decision_key == decision_key)
            )
            if existing:
                return DecisionResult.model_validate_json(existing.result_json)
            record = DecisionRecord(
                decision_id=str(result.decision_id),
                decision_key=decision_key,
                owner_id=owner_id,
                analysis_id=str(result.analysis_id) if result.analysis_id else None,
                symbol=result.symbol,
                strategy_key=result.strategy_key,
                strategy_version=result.strategy_version,
                status=result.status.value,
                reason_codes_json=_json_list(result.reason_codes),
                result_json=result.model_dump_json(),
                created_at=result.evaluated_at or _result_time(result),
            )
            session.add(record)
            if result.order_intent:
                intent = result.order_intent
                session.add(
                    OrderIntentRecord(
                        order_intent_id=str(intent.order_intent_id),
                        decision_id=str(result.decision_id),
                        owner_id=owner_id,
                        idempotency_key=intent.idempotency_key,
                        status="APPROVED",
                        intent_json=intent.model_dump_json(),
                        created_at=result.evaluated_at or _result_time(result),
                    )
                )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                concurrent = session.scalar(
                    select(DecisionRecord).where(DecisionRecord.decision_key == decision_key)
                )
                if concurrent is None:
                    raise
                return DecisionResult.model_validate_json(concurrent.result_json)
        return result

    def get(self, decision_id: UUID, *, owner_id: int) -> DecisionResult | None:
        with self._sessions() as session:
            record = session.scalar(
                select(DecisionRecord).where(
                    DecisionRecord.decision_id == str(decision_id), DecisionRecord.owner_id == owner_id
                )
            )
            return DecisionResult.model_validate_json(record.result_json) if record else None

    def get_for_analysis(self, analysis_id: UUID, *, owner_id: int) -> DecisionResult | None:
        statement = select(DecisionRecord).where(
            DecisionRecord.analysis_id == str(analysis_id),
            DecisionRecord.owner_id == owner_id,
        ).order_by(DecisionRecord.created_at.desc()).limit(1)
        with self._sessions() as session:
            record = session.scalar(statement)
            return DecisionResult.model_validate_json(record.result_json) if record else None

    def list_for_owner(
        self, *, owner_id: int, analysis_id: UUID | None = None
    ) -> list[DecisionResult]:
        statement = select(DecisionRecord).where(DecisionRecord.owner_id == owner_id)
        if analysis_id is not None:
            statement = statement.where(DecisionRecord.analysis_id == str(analysis_id))
        statement = statement.order_by(DecisionRecord.created_at.desc()).limit(500)
        with self._sessions() as session:
            records = session.scalars(statement).all()
            return [DecisionResult.model_validate_json(record.result_json) for record in records]

    def get_approved_intent(self, intent_id: UUID, *, owner_id: int) -> ApprovedOrderIntent | None:
        with self._sessions() as session:
            record = session.scalar(
                select(OrderIntentRecord).where(
                    OrderIntentRecord.order_intent_id == str(intent_id),
                    OrderIntentRecord.owner_id == owner_id,
                    OrderIntentRecord.status == "APPROVED",
                )
            )
            return ApprovedOrderIntent.model_validate_json(record.intent_json) if record else None


def _json_list(values: list[str]) -> str:
    import json

    return json.dumps(values, separators=(",", ":"))


def _result_time(result: DecisionResult):
    if result.order_intent and result.order_intent.expires_at:
        from datetime import timedelta

        return result.order_intent.expires_at - timedelta(seconds=1)
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
