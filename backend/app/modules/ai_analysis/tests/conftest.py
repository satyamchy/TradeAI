from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.ai_analysis.profiles import default_profile_registry
from app.modules.ai_analysis.repository import SqlAlchemyAnalysisRunRepository
from app.modules.ai_analysis.service import AIAnalysisService
from app.jobs.repository import SqlAlchemyAnalysisJobRepository
from app.jobs.service import AnalysisJobManager
from app.shared.contracts import (
    Candidate,
    CandidateValidationStatus,
    Instrument,
    SelectionMode,
)
from app.shared.database import create_engine_for_database, create_session_factory
from app.shared.migrations import migrate_database


class FakeCandidateLookup:
    def __init__(self, candidate: Candidate):
        self.candidate = candidate

    async def get_candidate(self, candidate_id, *, owner_id=None):
        if candidate_id != self.candidate.candidate_id or owner_id != 1:
            raise LookupError("candidate not found")
        return self.candidate


@pytest.fixture
def analysis_context(tmp_path: Path):
    database = tmp_path / "ai-analysis.db"
    migrate_database(database, backup_dir=tmp_path / "backups")
    engine = create_engine_for_database(database)
    sessions = create_session_factory(engine)
    candidate_id = uuid4()
    batch_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(username, password_hash, role, disabled, automation_state, automation_methods, created_at) "
                "VALUES ('ai-test-user', 'unused', 'trader', 0, 'off', '[]', '2026-10-30T00:00:00Z')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO candidate_batches "
                "(batch_id, created_by_user_id, selection_mode, exchange, horizon, status, "
                "submitted_symbols_json, rejected_symbols_json, rejections_json, created_at) "
                "VALUES (:batch, 1, 'MANUAL', 'NSE', 'INTRADAY', 'COMPLETED', '[]', '[]', '[]', :created)"
            ),
            {"batch": str(batch_id), "created": datetime.now(timezone.utc).isoformat()},
        )
        connection.execute(
            text(
                "INSERT INTO stock_candidates "
                "(candidate_id, batch_id, symbol, exchange, trading_symbol, analysis_ticker, security_id, "
                "segment, currency, selection_mode, selection_reason, validation_status, mapping_source, "
                "resolved_at, created_at) "
                "VALUES (:candidate, :batch, 'RELIANCE', 'NSE', 'RELIANCE', 'RELIANCE.NS', NULL, 'NSE_EQ', "
                "'INR', 'MANUAL', 'USER_SELECTED', 'ANALYSIS_ONLY', 'TEST_MASTER', :created, :created)"
            ),
            {
                "candidate": str(candidate_id),
                "batch": str(batch_id),
                "created": datetime.now(timezone.utc).isoformat(),
            },
        )
    candidate = Candidate(
        candidate_id=candidate_id,
        batch_id=batch_id,
        instrument=Instrument(
            symbol="RELIANCE",
            exchange="NSE",
            trading_symbol="RELIANCE",
            analysis_ticker="RELIANCE.NS",
            security_id=None,
            segment="NSE_EQ",
        ),
        selection_mode=SelectionMode.MANUAL,
        selection_reason="USER_SELECTED",
        validation_status=CandidateValidationStatus.ANALYSIS_ONLY,
        mapping_source="TEST_MASTER",
        resolved_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    yield {
        "engine": engine,
        "sessions": sessions,
        "candidate": candidate,
        "manager": AnalysisJobManager(SqlAlchemyAnalysisJobRepository(sessions)),
        "repository": SqlAlchemyAnalysisRunRepository(sessions),
        "profiles": default_profile_registry(),
        "candidate_lookup": FakeCandidateLookup(candidate),
    }
    engine.dispose()


@pytest.fixture
def make_analysis_service(analysis_context):
    def factory(provider, portfolio_provider=None):
        return AIAnalysisService(
            jobs=analysis_context["manager"],
            repository=analysis_context["repository"],
            candidates=analysis_context["candidate_lookup"],
            profiles=analysis_context["profiles"],
            provider=provider,
            portfolio_provider=portfolio_provider,
        )

    return factory
