"""Analysis job management and single in-process worker lifecycle."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.jobs.models import AnalysisJobRecord
from app.jobs.repository import SqlAlchemyAnalysisJobRepository
from app.jobs.schemas import AnalysisJobView
from app.shared.contracts import AnalysisStatus


class TransientAnalysisError(Exception):
    """A provider failure that may succeed on one retry."""


class PermanentAnalysisError(Exception):
    """A validation/provider failure that must not be retried."""


AnalysisHandler = Callable[[dict[str, Any]], Awaitable[str]]


class AnalysisJobManager:
    """Own idempotent job creation, safe status reads, and handler execution."""

    def __init__(self, repository: SqlAlchemyAnalysisJobRepository, *, max_attempts: int = 2):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self._repository = repository
        self._max_attempts = max_attempts

    def submit(
        self,
        *,
        owner_id: int,
        idempotency_key: str,
        request_payload: dict[str, Any],
    ) -> AnalysisJobView:
        record = self._repository.create_or_get(
            owner_id=owner_id,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
            max_attempts=self._max_attempts,
        )
        return _view(record)

    def get(self, analysis_id: UUID, *, owner_id: int) -> AnalysisJobView | None:
        record = self._repository.get(str(analysis_id), owner_id=owner_id)
        return _view(record) if record else None

    async def process_next(self, handler: AnalysisHandler) -> AnalysisJobView | None:
        record = self._repository.claim_next()
        if record is None:
            return None
        analysis_id = record.analysis_id
        request_payload = json.loads(record.request_json)
        try:
            result_reference = await handler(request_payload)
            completed = self._repository.complete(analysis_id, result_reference)
            return _view(completed)
        except TransientAnalysisError as exc:
            failed = self._repository.fail(
                analysis_id,
                failure_code="TRANSIENT_PROVIDER_ERROR",
                failure_message=str(exc),
                retryable=True,
            )
            return _view(failed)
        except PermanentAnalysisError as exc:
            failed = self._repository.fail(
                analysis_id,
                failure_code="PERMANENT_ANALYSIS_ERROR",
                failure_message=str(exc),
                retryable=False,
            )
            return _view(failed)
        except Exception:
            failed = self._repository.fail(
                analysis_id,
                failure_code="UNEXPECTED_ANALYSIS_ERROR",
                failure_message="Analysis failed unexpectedly.",
                retryable=False,
            )
            return _view(failed)

    def recover_running(self) -> int:
        return self._repository.recover_running()


class AnalysisJobWorker:
    """One bounded worker. It is constructed and started by FastAPI lifespan."""

    def __init__(
        self,
        manager: AnalysisJobManager,
        handler: AnalysisHandler,
        *,
        poll_interval_seconds: float = 0.5,
    ):
        self._manager = manager
        self._handler = handler
        self._poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._manager.recover_running()
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="analysis-job-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            job = await self._manager.process_next(self._handler)
            if job is None or job.status is AnalysisStatus.PENDING:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval_seconds)
                except asyncio.TimeoutError:
                    pass


def _view(record: AnalysisJobRecord) -> AnalysisJobView:
    return AnalysisJobView(
        analysis_id=UUID(record.analysis_id),
        idempotency_key=record.idempotency_key,
        status=AnalysisStatus(record.status),
        attempt_count=record.attempt_count,
        max_attempts=record.max_attempts,
        retryable=record.retryable,
        result_reference=record.result_reference,
        failure_code=record.failure_code,
        failure_message=record.failure_message,
        created_at=_aware_utc(record.created_at),
        updated_at=_aware_utc(record.updated_at),
        started_at=_aware_utc(record.started_at) if record.started_at else None,
        completed_at=_aware_utc(record.completed_at) if record.completed_at else None,
    )


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
