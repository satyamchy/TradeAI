"""SQLAlchemy repository for candidate batches and candidate records."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.modules.stock_selection.models import CandidateBatchRecord, StockCandidateRecord
from app.modules.stock_selection.schemas import CandidateFilters
from app.shared.contracts import Candidate, CandidateBatch, Instrument


class CandidateRepository(Protocol):
    """Persistence boundary injected into the public service."""

    def create_batch(
        self,
        batch: CandidateBatch,
        request_symbols: list[str],
        owner_id: int | None,
        *,
        exchange: str,
        horizon: str,
    ) -> None:
        ...

    def get_candidate(self, candidate_id: UUID, owner_id: int | None) -> Candidate | None:
        ...

    def list_candidates(self, filters: CandidateFilters, owner_id: int | None) -> list[Candidate]:
        ...


class SqlAlchemyCandidateRepository:
    """Short-lived transactions bound to the application session factory."""

    def __init__(self, sessions: sessionmaker[Session]):
        self._sessions = sessions

    def create_batch(
        self,
        batch: CandidateBatch,
        request_symbols: list[str],
        owner_id: int | None,
        *,
        exchange: str,
        horizon: str,
    ) -> None:
        batch_record = CandidateBatchRecord(
            batch_id=str(batch.batch_id),
            created_by_user_id=owner_id,
            selection_mode="MANUAL",
            exchange=exchange,
            horizon=horizon,
            status=batch.status.value,
            submitted_symbols_json=json.dumps(request_symbols, ensure_ascii=False),
            rejected_symbols_json=json.dumps(batch.rejected_symbols, ensure_ascii=False),
            rejections_json=json.dumps(
                [rejection.model_dump(mode="json") for rejection in batch.rejections],
                ensure_ascii=False,
                sort_keys=True,
            ),
            created_at=batch.created_at,
        )
        with self._sessions.begin() as session:
            session.add(batch_record)
            session.add_all(
                [
                    StockCandidateRecord(
                        candidate_id=str(candidate.candidate_id),
                        batch_id=str(candidate.batch_id),
                        symbol=candidate.instrument.symbol,
                        exchange=candidate.instrument.exchange,
                        trading_symbol=candidate.instrument.trading_symbol,
                        analysis_ticker=candidate.instrument.analysis_ticker,
                        security_id=candidate.instrument.security_id,
                        segment=candidate.instrument.segment,
                        currency=candidate.instrument.currency,
                        selection_mode=candidate.selection_mode.value,
                        selection_reason=candidate.selection_reason,
                        validation_status=candidate.validation_status.value,
                        mapping_source=candidate.mapping_source,
                        resolved_at=candidate.resolved_at,
                        created_at=candidate.created_at,
                    )
                    for candidate in batch.candidates
                ]
            )

    def get_candidate(self, candidate_id: UUID, owner_id: int | None) -> Candidate | None:
        statement = (
            select(StockCandidateRecord)
            .join(CandidateBatchRecord, StockCandidateRecord.batch_id == CandidateBatchRecord.batch_id)
            .where(StockCandidateRecord.candidate_id == str(candidate_id))
        )
        if owner_id is not None:
            statement = statement.where(CandidateBatchRecord.created_by_user_id == owner_id)
        with self._sessions() as session:
            record = session.scalar(statement)
            return _to_candidate(record) if record else None

    def list_candidates(self, filters: CandidateFilters, owner_id: int | None) -> list[Candidate]:
        statement = (
            select(StockCandidateRecord)
            .join(CandidateBatchRecord, StockCandidateRecord.batch_id == CandidateBatchRecord.batch_id)
        )
        if owner_id is not None:
            statement = statement.where(CandidateBatchRecord.created_by_user_id == owner_id)
        if filters.exchange:
            statement = statement.where(StockCandidateRecord.exchange == filters.exchange.upper())
        if filters.selection_mode:
            statement = statement.where(StockCandidateRecord.selection_mode == filters.selection_mode)
        if filters.horizon:
            statement = statement.where(CandidateBatchRecord.horizon == filters.horizon.upper())
        if filters.created_after:
            statement = statement.where(StockCandidateRecord.created_at >= filters.created_after)
        if filters.created_before:
            statement = statement.where(StockCandidateRecord.created_at <= filters.created_before)
        statement = statement.order_by(StockCandidateRecord.created_at.desc()).limit(filters.limit).offset(filters.offset)
        with self._sessions() as session:
            records = session.scalars(statement).all()
            return [_to_candidate(record) for record in records]


def _to_candidate(record: StockCandidateRecord) -> Candidate:
    return Candidate(
        candidate_id=UUID(record.candidate_id),
        batch_id=UUID(record.batch_id),
        instrument=Instrument(
            symbol=record.symbol,
            exchange=record.exchange,
            trading_symbol=record.trading_symbol,
            analysis_ticker=record.analysis_ticker,
            security_id=record.security_id,
            segment=record.segment,
            currency=record.currency,
        ),
        selection_mode=record.selection_mode,
        selection_reason=record.selection_reason,
        validation_status=record.validation_status,
        mapping_source=record.mapping_source,
        resolved_at=_as_utc(record.resolved_at),
        created_at=_as_utc(record.created_at),
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
