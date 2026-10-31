"""SQLAlchemy job persistence. Session factories are injected by the composition root."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.jobs.models import AnalysisJobRecord


SENSITIVE_MARKERS = (
    "token", "apikey", "secret", "password", "authorization", "credential", "privatekey", "accesskey",
)


def sanitize_payload(value: Any) -> Any:
    """Copy JSON-like input while replacing credential-shaped values."""
    if isinstance(value, dict):
        import re

        clean: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            normalized = re.sub(r"[^a-z0-9]", "", name.lower())
            sensitive = any(marker in normalized for marker in SENSITIVE_MARKERS)
            clean[name] = "[REDACTED]" if sensitive else sanitize_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("analysis job payload must contain JSON-compatible values")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SqlAlchemyAnalysisJobRepository:
    """Synchronous repository with short, injected SQLAlchemy transactions."""

    def __init__(self, sessions: sessionmaker[Session]):
        self._sessions = sessions

    def create_or_get(
        self,
        *,
        analysis_id: str | None = None,
        owner_id: int,
        idempotency_key: str,
        request_payload: dict[str, Any],
        max_attempts: int = 2,
    ) -> AnalysisJobRecord:
        now = utc_now()
        record = AnalysisJobRecord(
            analysis_id=analysis_id or str(uuid4()),
            created_by_user_id=owner_id,
            idempotency_key=idempotency_key,
            status="PENDING",
            request_json=json.dumps(sanitize_payload(request_payload), sort_keys=True, separators=(",", ":")),
            attempt_count=0,
            max_attempts=max_attempts,
            retryable=False,
            created_at=now,
            updated_at=now,
        )
        try:
            with self._sessions.begin() as session:
                session.add(record)
                session.flush()
            return record
        except IntegrityError:
            with self._sessions() as session:
                existing = session.scalar(
                    select(AnalysisJobRecord).where(
                        AnalysisJobRecord.created_by_user_id == owner_id,
                        AnalysisJobRecord.idempotency_key == idempotency_key,
                    )
                )
                if existing is None:
                    raise
                return existing

    def get(self, analysis_id: str, *, owner_id: int) -> AnalysisJobRecord | None:
        with self._sessions() as session:
            record = session.scalar(
                select(AnalysisJobRecord).where(
                    AnalysisJobRecord.analysis_id == analysis_id,
                    AnalysisJobRecord.created_by_user_id == owner_id,
                )
            )
            return record

    def get_request_payload(self, analysis_id: str, *, owner_id: int) -> dict[str, Any] | None:
        record = self.get(analysis_id, owner_id=owner_id)
        return json.loads(record.request_json) if record is not None else None

    def claim_next(self, analysis_id: str | None = None) -> AnalysisJobRecord | None:
        with self._sessions.begin() as session:
            statement = select(AnalysisJobRecord).where(AnalysisJobRecord.status == "PENDING")
            if analysis_id is not None:
                statement = statement.where(AnalysisJobRecord.analysis_id == analysis_id)
            statement = statement.order_by(AnalysisJobRecord.created_at, AnalysisJobRecord.analysis_id).limit(1)
            candidate = session.scalar(statement)
            if candidate is None:
                return None
            now = utc_now()
            claimed = session.execute(
                update(AnalysisJobRecord)
                .where(
                    AnalysisJobRecord.analysis_id == candidate.analysis_id,
                    AnalysisJobRecord.status == "PENDING",
                )
                .values(
                    status="RUNNING",
                    attempt_count=AnalysisJobRecord.attempt_count + 1,
                    updated_at=now,
                    started_at=now,
                    failure_code=None,
                    failure_message=None,
                    retryable=False,
                )
            )
            if claimed.rowcount != 1:
                return None
            session.flush()
            return session.get(AnalysisJobRecord, candidate.analysis_id)

    def complete(self, analysis_id: str, result_reference: str) -> AnalysisJobRecord:
        now = utc_now()
        with self._sessions.begin() as session:
            record = session.get(AnalysisJobRecord, analysis_id)
            if record is None or record.status != "RUNNING":
                raise ValueError("only a running analysis job can complete")
            record.status = "COMPLETED"
            record.result_reference = result_reference[:500]
            record.failure_code = None
            record.failure_message = None
            record.retryable = False
            record.updated_at = now
            record.completed_at = now
            return record

    def fail(
        self,
        analysis_id: str,
        *,
        failure_code: str,
        failure_message: str,
        retryable: bool,
    ) -> AnalysisJobRecord:
        now = utc_now()
        safe_code = _safe_code(failure_code)
        safe_message = _redact_message(failure_message)
        with self._sessions.begin() as session:
            record = session.get(AnalysisJobRecord, analysis_id)
            if record is None or record.status != "RUNNING":
                raise ValueError("only a running analysis job can fail")
            should_retry = retryable and record.attempt_count < record.max_attempts
            record.status = "PENDING" if should_retry else "FAILED"
            record.failure_code = safe_code
            record.failure_message = safe_message
            record.retryable = should_retry
            record.updated_at = now
            record.completed_at = None if should_retry else now
            return record

    def recover_running(self) -> int:
        """Return abandoned jobs to the queue once, preserving their analysis IDs."""
        now = utc_now()
        count = 0
        with self._sessions.begin() as session:
            records = session.scalars(
                select(AnalysisJobRecord).where(AnalysisJobRecord.status == "RUNNING")
            ).all()
            for record in records:
                retry = record.attempt_count < record.max_attempts
                record.status = "PENDING" if retry else "FAILED"
                record.retryable = retry
                record.failure_code = "WORKER_RESTARTED"
                record.failure_message = "Analysis worker stopped before recording a result."
                record.updated_at = now
                record.completed_at = None if retry else now
                count += 1
        return count


def _safe_code(value: str) -> str:
    safe = "".join(char for char in value.upper() if char.isalnum() or char in "_-")
    return (safe or "ANALYSIS_FAILED")[:64]


def _redact_message(value: str) -> str:
    import re

    safe = re.sub(
        r"(?i)([a-z0-9_-]*(?:token|client[_ -]?id|api[_ -]?(?:key|secret)|password|secret|authorization|credential|private[_ -]?key)[a-z0-9_-]*)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        value,
    )
    return safe[:500]
