import asyncio
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.jobs.models import AnalysisJobRecord
from app.jobs.service import AnalysisJobManager
from app.modules.ai_analysis.providers import (
    PermanentProviderFailure,
    TransientProviderFailure,
)
from app.modules.ai_analysis.repository import AnalysisRunRecord, SqlAlchemyAnalysisRunRepository
from app.modules.ai_analysis.schemas import (
    AnalysisProviderOutput,
    PortfolioSnapshotReference,
    PortfolioPosition,
)
from app.modules.ai_analysis.service import (
    AIAnalysisError,
    AnalysisNotReady,
    CandidateUnavailable,
    InvalidAnalysisRequest,
)
from app.shared.contracts import AnalysisRequest, AnalysisStatus, ProviderName


def request_for(candidate_id, **overrides):
    payload = {
        "candidate_id": candidate_id,
        "provider": ProviderName.TRADING_AGENTS,
        "analysis_date": date(2026, 10, 30),
        "horizon": "INTRADAY",
        "analysis_profile_key": "INTRADAY_RESEARCH",
        "analysis_profile_version": "1",
        "selected_analysts": [],
        "include_portfolio_context": False,
        "checkpoint_enabled": False,
        "save_html_report": True,
    }
    payload.update(overrides)
    return AnalysisRequest.model_validate(payload)


class FakeProvider:
    version = "test-provider-1"

    def __init__(self, output=None, fail_once=None, permanent_error=None):
        self.output = output or AnalysisProviderOutput(
            provider_version="0.7.1",
            source_rating="Overweight",
            reports={"market": "market note", "portfolio_decision": "Rating: Overweight"},
            report_artifacts={"html_report_path": "test/reports/report.html", "report_checksum": "sha256:test"},
        )
        self.fail_once = fail_once
        self.permanent_error = permanent_error
        self.calls = []

    async def analyze(self, request):
        self.calls.append(request)
        if self.fail_once is not None:
            error, self.fail_once = self.fail_once, None
            raise error
        if self.permanent_error is not None:
            raise self.permanent_error
        return self.output


class FakePortfolioProvider:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    async def get_snapshot(self, *, owner_id):
        assert owner_id == 1
        return self.snapshot


def test_analysis_request_persists_profile_result_and_is_owner_scoped(analysis_context, make_analysis_service):
    provider = FakeProvider()
    service = make_analysis_service(provider)
    request = request_for(analysis_context["candidate"].candidate_id)

    receipt = asyncio.run(service.request_analysis(request, owner_id=1, idempotency_key="analysis-1"))
    duplicate = asyncio.run(service.request_analysis(request, owner_id=1, idempotency_key="analysis-1"))
    result = asyncio.run(service.run_analysis_job(receipt.analysis_id))

    assert receipt.analysis_id == duplicate.analysis_id
    assert receipt.status is AnalysisStatus.PENDING
    assert receipt.candidate_id == analysis_context["candidate"].candidate_id
    assert result.analysis_id == receipt.analysis_id
    assert result.status is AnalysisStatus.COMPLETED
    assert result.provider is ProviderName.TRADING_AGENTS
    assert result.provider_version == "0.7.1"
    assert result.source_rating == "Overweight"
    assert result.direction.value == "BULLISH"
    assert result.quick_provider == "groq"
    assert result.selected_analysts == ["market", "social", "news", "fundamentals"]
    assert result.warnings == ["PORTFOLIO_CONTEXT_NOT_INCLUDED"]
    assert asyncio.run(service.get_analysis(receipt.analysis_id, owner_id=1)) == result
    assert asyncio.run(service.get_analysis(receipt.analysis_id, owner_id=2)) is None
    assert asyncio.run(service.list_analyses(filters_for(result.candidate_id), owner_id=1)) == [result]

    with analysis_context["sessions"]() as session:
        run = session.get(AnalysisRunRecord, str(receipt.analysis_id))
        job = session.get(AnalysisJobRecord, str(receipt.analysis_id))
        assert run is not None and run.status == "COMPLETED"
        assert job is not None and job.status == "COMPLETED"
        assert "quick_model" in run.run_config_json
        assert session.scalar(select(AnalysisJobRecord.analysis_id).where(
            AnalysisJobRecord.idempotency_key == "analysis-1"
        )) == str(receipt.analysis_id)


def filters_for(candidate_id):
    from app.modules.ai_analysis.schemas import AnalysisFilters

    return AnalysisFilters(candidate_id=candidate_id)


def test_explicit_flat_portfolio_is_distinct_from_missing_context(analysis_context, make_analysis_service):
    snapshot_id = uuid4()
    snapshot = PortfolioSnapshotReference(
        snapshot_id=snapshot_id,
        captured_at=datetime.now(timezone.utc),
        currency="INR",
        cash=0,
        positions=[],
    )
    provider = FakeProvider()
    service = make_analysis_service(provider, FakePortfolioProvider(snapshot))
    request = request_for(
        analysis_context["candidate"].candidate_id,
        include_portfolio_context=True,
    )

    receipt = asyncio.run(service.request_analysis(request, owner_id=1, idempotency_key="flat-book"))
    result = asyncio.run(service.run_analysis_job(receipt.analysis_id))

    assert provider.calls[0].portfolio is not None
    assert provider.calls[0].portfolio.positions == []
    assert result.portfolio_snapshot_id == snapshot_id
    assert "PORTFOLIO_CONTEXT_NOT_INCLUDED" not in result.warnings


def test_stale_optional_portfolio_is_omitted_with_warning(analysis_context, make_analysis_service):
    snapshot = PortfolioSnapshotReference(
        snapshot_id=uuid4(),
        captured_at=datetime.now(timezone.utc) - timedelta(hours=1),
        currency="INR",
        cash=1000,
        positions=[PortfolioPosition(ticker="RELIANCE", quantity=1, average_price=100)],
    )
    provider = FakeProvider()
    service = make_analysis_service(provider, FakePortfolioProvider(snapshot))
    request = request_for(analysis_context["candidate"].candidate_id, include_portfolio_context=True)

    receipt = asyncio.run(service.request_analysis(request, owner_id=1, idempotency_key="stale-book"))
    result = asyncio.run(service.run_analysis_job(receipt.analysis_id))

    assert provider.calls[0].portfolio is None
    assert result.portfolio_snapshot_id is None
    assert "PORTFOLIO_CONTEXT_STALE" in result.warnings


def test_transient_provider_failure_retries_once_with_same_analysis_id(analysis_context, make_analysis_service):
    provider = FakeProvider(fail_once=TransientProviderFailure("transient"))
    service = make_analysis_service(provider)
    request = request_for(analysis_context["candidate"].candidate_id)
    receipt = asyncio.run(service.request_analysis(request, owner_id=1, idempotency_key="transient"))

    with pytest.raises(AnalysisNotReady):
        asyncio.run(service.run_analysis_job(receipt.analysis_id))
    retried = asyncio.run(service.run_analysis_job(receipt.analysis_id))
    job = analysis_context["manager"].get(receipt.analysis_id, owner_id=1)

    assert retried.analysis_id == receipt.analysis_id
    assert len(provider.calls) == 2
    assert job is not None and job.status is AnalysisStatus.COMPLETED
    assert job.attempt_count == 2


def test_permanent_provider_failure_is_sanitized_and_not_retried(analysis_context, make_analysis_service):
    provider = FakeProvider(permanent_error=PermanentProviderFailure("bad provider settings"))
    service = make_analysis_service(provider)
    request = request_for(analysis_context["candidate"].candidate_id)
    receipt = asyncio.run(service.request_analysis(request, owner_id=1, idempotency_key="permanent"))

    with pytest.raises(AIAnalysisError, match="bad provider settings"):
        asyncio.run(service.run_analysis_job(receipt.analysis_id))
    job = analysis_context["manager"].get(receipt.analysis_id, owner_id=1)
    assert job is not None and job.status is AnalysisStatus.FAILED
    assert job.attempt_count == 1


def test_invalid_provider_analyst_and_candidate_fail_before_job_creation(analysis_context, make_analysis_service):
    provider = FakeProvider()
    service = make_analysis_service(provider)
    bad_request = request_for(
        analysis_context["candidate"].candidate_id,
        selected_analysts=["unsupported"],
    )
    with pytest.raises(InvalidAnalysisRequest):
        asyncio.run(service.request_analysis(bad_request, owner_id=1, idempotency_key="bad-analyst"))
    with pytest.raises(CandidateUnavailable):
        asyncio.run(service.request_analysis(
            request_for(uuid4()), owner_id=1, idempotency_key="missing-candidate"
        ))
    assert provider.calls == []


def test_other_provider_and_future_date_are_rejected(analysis_context, make_analysis_service):
    service = make_analysis_service(FakeProvider())
    with pytest.raises(InvalidAnalysisRequest, match="Only the TRADING_AGENTS"):
        asyncio.run(service.request_analysis(
            request_for(analysis_context["candidate"].candidate_id, provider="LEGACY_LANGGRAPH"),
            owner_id=1,
            idempotency_key="provider",
        ))
    future_date = datetime.now(timezone.utc).date() + timedelta(days=1)
    with pytest.raises(InvalidAnalysisRequest, match="future"):
        asyncio.run(service.request_analysis(
            request_for(analysis_context["candidate"].candidate_id, analysis_date=future_date),
            owner_id=1,
            idempotency_key="future",
        ))
