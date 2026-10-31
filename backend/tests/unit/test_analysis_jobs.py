import asyncio
import json
import sqlite3
from pathlib import Path

from sqlalchemy import select

from app.jobs.models import AnalysisJobRecord
from app.jobs.repository import SqlAlchemyAnalysisJobRepository
from app.jobs.service import (
    AnalysisJobManager,
    AnalysisJobWorker,
    PermanentAnalysisError,
    TransientAnalysisError,
)
from app.shared.database import create_engine_for_database, create_session_factory
from app.shared.migrations import migrate_database


def _manager(tmp_path: Path) -> tuple[AnalysisJobManager, object]:
    database = tmp_path / "jobs.db"
    migrate_database(database, backup_dir=tmp_path / "backups")
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            ("job-user", "fixture-hash", "trader", "2026-01-01T00:00:00+00:00"),
        )
        connection.commit()
    finally:
        connection.close()
    engine = create_engine_for_database(database)
    sessions = create_session_factory(engine)
    manager = AnalysisJobManager(SqlAlchemyAnalysisJobRepository(sessions))
    return manager, engine


def test_idempotency_persists_pending_job_and_sanitizes_request(tmp_path):
    manager, engine = _manager(tmp_path)
    try:
        first = manager.submit(
            owner_id=1,
            idempotency_key="request-1",
            request_payload={"symbol": "TESTCO", "access_token": "do-not-store"},
        )
        duplicate = manager.submit(
            owner_id=1,
            idempotency_key="request-1",
            request_payload={"symbol": "TESTCO"},
        )

        assert first.analysis_id == duplicate.analysis_id
        assert first.status.value == "PENDING"
        assert first.attempt_count == 0
        with create_session_factory(engine)() as session:
            stored = session.scalar(select(AnalysisJobRecord).where(AnalysisJobRecord.analysis_id == str(first.analysis_id)))
            assert stored is not None
            assert "do-not-store" not in stored.request_json
            assert json.loads(stored.request_json)["access_token"] == "[REDACTED]"
        assert manager.get(first.analysis_id, owner_id=2) is None
    finally:
        engine.dispose()


def test_transient_failure_retries_once_with_same_analysis_id(tmp_path):
    manager, engine = _manager(tmp_path)
    try:
        created = manager.submit(owner_id=1, idempotency_key="retry", request_payload={"symbol": "TESTCO"})

        async def fail_transiently(_payload):
            raise TransientAnalysisError("provider timeout access_token=must-not-persist")

        first = asyncio.run(manager.process_next(fail_transiently))
        second = asyncio.run(manager.process_next(fail_transiently))

        assert first is not None and first.status.value == "PENDING"
        assert first.analysis_id == created.analysis_id and first.attempt_count == 1
        assert first.retryable is True
        assert "must-not-persist" not in (first.failure_message or "")
        assert "[REDACTED]" in (first.failure_message or "")
        assert second is not None and second.status.value == "FAILED"
        assert second.analysis_id == created.analysis_id and second.attempt_count == 2
        assert second.failure_code == "TRANSIENT_PROVIDER_ERROR"
    finally:
        engine.dispose()


def test_permanent_failure_is_not_retried_and_success_stores_only_reference(tmp_path):
    manager, engine = _manager(tmp_path)
    try:
        failed_job = manager.submit(owner_id=1, idempotency_key="permanent", request_payload={})

        async def fail_permanently(_payload):
            raise PermanentAnalysisError("invalid provider profile")

        failed = asyncio.run(manager.process_next(fail_permanently))
        assert failed is not None and failed.status.value == "FAILED"
        assert failed.attempt_count == 1
        assert failed.retryable is False

        success_job = manager.submit(owner_id=1, idempotency_key="success", request_payload={"symbol": "TESTCO"})

        async def complete(_payload):
            return "reports/analysis/testco.json"

        completed = asyncio.run(manager.process_next(complete))
        assert completed is not None and completed.status.value == "COMPLETED"
        assert completed.analysis_id == success_job.analysis_id
        assert completed.result_reference == "reports/analysis/testco.json"
        assert failed_job.analysis_id != success_job.analysis_id
    finally:
        engine.dispose()


def test_worker_restart_requeues_or_fails_without_changing_id(tmp_path):
    manager, engine = _manager(tmp_path)
    try:
        created = manager.submit(owner_id=1, idempotency_key="restart", request_payload={})
        repository = manager._repository
        claimed = repository.claim_next()
        assert claimed is not None and claimed.analysis_id == str(created.analysis_id)
        assert repository.recover_running() == 1
        recovered = manager.get(created.analysis_id, owner_id=1)
        assert recovered is not None and recovered.status.value == "PENDING"
        assert recovered.analysis_id == created.analysis_id
        assert recovered.attempt_count == 1
    finally:
        engine.dispose()


def test_single_worker_picks_up_persisted_pending_job(tmp_path):
    manager, engine = _manager(tmp_path)
    try:
        created = manager.submit(owner_id=1, idempotency_key="worker", request_payload={"symbol": "TESTCO"})
        calls = []

        async def handle(payload):
            calls.append(payload["symbol"])
            return "reports/worker-result.json"

        async def run_worker():
            worker = AnalysisJobWorker(manager, handle, poll_interval_seconds=0.01)
            await worker.start()
            for _ in range(100):
                job = manager.get(created.analysis_id, owner_id=1)
                if job is not None and job.status.value == "COMPLETED":
                    break
                await asyncio.sleep(0.01)
            await worker.stop()
            return manager.get(created.analysis_id, owner_id=1)

        completed = asyncio.run(run_worker())
        assert completed is not None and completed.status.value == "COMPLETED"
        assert completed.result_reference == "reports/worker-result.json"
        assert calls == ["TESTCO"]
    finally:
        engine.dispose()
