"""SQLAlchemy repository for normalized Module 2 analysis results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.jobs.models import AnalysisJobRecord
from app.modules.ai_analysis.models import AnalysisRunRecord
from app.modules.ai_analysis.schemas import AnalysisFilters
from app.shared.contracts import AnalysisResult


class SqlAlchemyAnalysisRunRepository:
    def __init__(self, sessions: sessionmaker[Session]):
        self._sessions = sessions

    def create_pending(
        self,
        *,
        analysis_id: UUID,
        candidate_id: UUID,
        provider: str,
        provider_version: str,
        profile_key: str,
        profile_version: str,
        run_config: dict[str, Any],
    ) -> tuple[UUID, str]:
        with self._sessions.begin() as session:
            existing = session.get(AnalysisRunRecord, str(analysis_id))
            if existing is not None:
                return UUID(existing.candidate_id), existing.provider
            session.add(
                AnalysisRunRecord(
                    analysis_id=str(analysis_id),
                    candidate_id=str(candidate_id),
                    provider=provider,
                    provider_version=provider_version,
                    profile_key=profile_key,
                    profile_version=profile_version,
                    status="PENDING",
                    run_config_json=json.dumps(run_config, sort_keys=True, separators=(",", ":")),
                    created_at=_utc_now(),
                )
            )
            session.flush()
            return candidate_id, provider

    def mark_running(self, analysis_id: UUID) -> datetime:
        started_at = _utc_now()
        with self._sessions.begin() as session:
            record = session.get(AnalysisRunRecord, str(analysis_id))
            if record is None:
                raise ValueError("analysis run was not created before execution")
            record.status = "RUNNING"
            record.started_at = started_at
            record.completed_at = None
        return started_at

    def mark_pending(self, analysis_id: UUID) -> None:
        with self._sessions.begin() as session:
            record = session.get(AnalysisRunRecord, str(analysis_id))
            if record is not None and record.result_json is None:
                record.status = "PENDING"
                record.started_at = None
                record.completed_at = None

    def mark_failed(self, analysis_id: UUID) -> None:
        with self._sessions.begin() as session:
            record = session.get(AnalysisRunRecord, str(analysis_id))
            if record is not None and record.result_json is None:
                record.status = "FAILED"
                record.completed_at = _utc_now()

    def complete(
        self,
        result: AnalysisResult,
        *,
        provider_version: str,
        started_at: datetime,
    ) -> None:
        with self._sessions.begin() as session:
            record = session.get(AnalysisRunRecord, str(result.analysis_id))
            if record is None:
                raise ValueError("analysis run was not created before completion")
            record.provider_version = provider_version
            record.status = result.status.value
            record.result_json = result.model_dump_json()
            record.started_at = started_at
            record.completed_at = result.completed_at or _utc_now()

    def get(self, analysis_id: UUID, *, owner_id: int) -> AnalysisResult | None:
        statement = (
            select(AnalysisRunRecord.result_json)
            .join(AnalysisJobRecord, AnalysisRunRecord.analysis_id == AnalysisJobRecord.analysis_id)
            .where(
                AnalysisRunRecord.analysis_id == str(analysis_id),
                AnalysisJobRecord.created_by_user_id == owner_id,
            )
        )
        with self._sessions() as session:
            payload = session.scalar(statement)
        return AnalysisResult.model_validate_json(payload) if payload else None

    def get_internal(self, analysis_id: UUID) -> AnalysisResult | None:
        """Worker-only result lookup after the owner-scoped request was authorized."""
        with self._sessions() as session:
            payload = session.scalar(
                select(AnalysisRunRecord.result_json).where(AnalysisRunRecord.analysis_id == str(analysis_id))
            )
        return AnalysisResult.model_validate_json(payload) if payload else None

    def list(self, filters: AnalysisFilters, *, owner_id: int) -> list[AnalysisResult]:
        statement = (
            select(AnalysisRunRecord.result_json)
            .join(AnalysisJobRecord, AnalysisRunRecord.analysis_id == AnalysisJobRecord.analysis_id)
            .where(
                AnalysisJobRecord.created_by_user_id == owner_id,
                AnalysisRunRecord.result_json.is_not(None),
            )
        )
        if filters.candidate_id is not None:
            statement = statement.where(AnalysisRunRecord.candidate_id == str(filters.candidate_id))
        if filters.created_after is not None:
            statement = statement.where(AnalysisRunRecord.created_at >= filters.created_after)
        if filters.created_before is not None:
            statement = statement.where(AnalysisRunRecord.created_at <= filters.created_before)
        statement = statement.order_by(AnalysisRunRecord.created_at.desc()).limit(filters.limit).offset(filters.offset)
        with self._sessions() as session:
            payloads = session.scalars(statement).all()
        return [AnalysisResult.model_validate_json(payload) for payload in payloads if payload]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
