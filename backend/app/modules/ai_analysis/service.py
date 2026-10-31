"""Public AI Analysis service with durable, replaceable background job handling."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.jobs.service import (
    AnalysisJobManager,
    PermanentAnalysisError,
    TransientAnalysisError,
)
from app.modules.ai_analysis.profiles import AnalysisProfileRegistry
from app.modules.ai_analysis.providers import (
    AnalysisProvider,
    PermanentProviderFailure,
    TransientProviderFailure,
    normalize_direction,
)
from app.modules.ai_analysis.repository import SqlAlchemyAnalysisRunRepository
from app.modules.ai_analysis.schemas import (
    AnalysisFilters,
    AnalysisProfile,
    AnalysisProviderOutput,
    AnalysisProviderRequest,
    PortfolioSnapshotReference,
)
from app.shared.contracts import (
    AnalysisDirection,
    AnalysisJobReceipt,
    AnalysisRequest,
    AnalysisResult,
    AnalysisStatus,
    Candidate,
    ProviderName,
)
from app.shared.logging import bind_log_context, get_logger, reset_log_context

logger = get_logger(__name__)


class CandidateLookup(Protocol):
    """Typed public candidate lookup injected by the workflow/composition root."""

    async def get_candidate(self, candidate_id: UUID, *, owner_id: int | None = None) -> Candidate:
        ...


class PortfolioSnapshotProvider(Protocol):
    """Return an authoritative application account snapshot, never caller JSON."""

    async def get_snapshot(self, *, owner_id: int) -> PortfolioSnapshotReference | None:
        ...


class AIAnalysisError(RuntimeError):
    """Base typed service error translated at the API boundary."""


class InvalidAnalysisRequest(AIAnalysisError):
    """The request conflicts with its registered profile or candidate."""


class CandidateUnavailable(AIAnalysisError):
    """The candidate does not exist or is outside the caller's scope."""


class AnalysisNotFound(AIAnalysisError):
    """The requested analysis job/result is unavailable to this caller."""


class AnalysisNotReady(AIAnalysisError):
    """A valid analysis has not completed yet."""


class AIAnalysisService:
    """Accept validated research requests and normalize provider results."""

    def __init__(
        self,
        *,
        jobs: AnalysisJobManager,
        repository: SqlAlchemyAnalysisRunRepository,
        candidates: CandidateLookup,
        profiles: AnalysisProfileRegistry,
        provider: AnalysisProvider,
        portfolio_provider: PortfolioSnapshotProvider | None = None,
        provider_version: str = "0.7.1",
    ):
        self._jobs = jobs
        self._repository = repository
        self._candidates = candidates
        self._profiles = profiles
        self._provider = provider
        self._portfolio_provider = portfolio_provider
        self._provider_version = provider_version

    async def request_analysis(
        self,
        request: AnalysisRequest,
        *,
        owner_id: int,
        idempotency_key: str,
    ) -> AnalysisJobReceipt:
        tokens = bind_log_context(module="ai_analysis")
        try:
            return await self._request_analysis(
                request,
                owner_id=owner_id,
                idempotency_key=idempotency_key,
            )
        finally:
            reset_log_context(tokens)

    async def submit(
        self,
        request: AnalysisRequest,
        *,
        owner_id: int,
        idempotency_key: str,
    ) -> AnalysisJobReceipt:
        """Public alias retained for callers of the original Phase 1 protocol."""
        return await self.request_analysis(request, owner_id=owner_id, idempotency_key=idempotency_key)

    async def _request_analysis(
        self,
        request: AnalysisRequest,
        *,
        owner_id: int,
        idempotency_key: str,
    ) -> AnalysisJobReceipt:
        if request.provider is not ProviderName.TRADING_AGENTS:
            raise InvalidAnalysisRequest("Only the TRADING_AGENTS provider is registered")
        if not idempotency_key.strip() or len(idempotency_key) > 128:
            raise InvalidAnalysisRequest("A 1–128 character idempotency key is required")
        if request.analysis_date > datetime.now(ZoneInfo("Asia/Kolkata")).date():
            raise InvalidAnalysisRequest("Analysis date cannot be in the future")

        profile = self._profiles.resolve(request.analysis_profile_key, request.analysis_profile_version)
        if request.horizon is not profile.horizon:
            raise InvalidAnalysisRequest("Requested horizon does not match the selected profile")
        profile = _request_profile_overrides(profile, request)
        try:
            candidate = await self._candidates.get_candidate(request.candidate_id, owner_id=owner_id)
        except Exception as exc:
            raise CandidateUnavailable("Candidate is unavailable") from exc
        if not candidate.instrument.analysis_ticker:
            raise InvalidAnalysisRequest("Candidate has no resolved analysis ticker")

        portfolio, warnings = await self._resolve_portfolio(request, profile, owner_id)
        proposed_analysis_id = uuid4()
        request_payload = {
            "analysis_id": str(proposed_analysis_id),
            "candidate": candidate.model_dump(mode="json"),
            "request": request.model_dump(mode="json"),
            "profile": profile.model_dump(mode="json"),
            "portfolio": portfolio.model_dump(mode="json") if portfolio is not None else None,
            "warnings": warnings,
        }
        job = self._jobs.submit(
            analysis_id=proposed_analysis_id,
            owner_id=owner_id,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
        )
        effective_payload = self._jobs.get_request_payload(job.analysis_id, owner_id=owner_id) or request_payload
        effective_candidate = Candidate.model_validate(effective_payload["candidate"])
        effective_request = AnalysisRequest.model_validate(effective_payload["request"])
        effective_profile = AnalysisProfile.model_validate(effective_payload["profile"])
        run_config = _run_config_snapshot(
            effective_request,
            effective_profile,
            effective_payload.get("portfolio"),
        )
        provider_version = str(getattr(self._provider, "version", self._provider_version))
        candidate_id, provider_name = self._repository.create_pending(
            analysis_id=job.analysis_id,
            candidate_id=effective_candidate.candidate_id,
            provider=effective_request.provider.value,
            provider_version=provider_version,
            profile_key=effective_profile.key,
            profile_version=effective_profile.version,
            run_config=run_config,
        )
        return AnalysisJobReceipt(
            analysis_id=job.analysis_id,
            candidate_id=candidate_id,
            status=job.status,
            provider=ProviderName(provider_name),
            created_at=job.created_at,
        )

    async def run_analysis_job(self, job_id: UUID) -> AnalysisResult:
        """Worker entry point for one queued job; retries retain the same ID."""
        job = await self._jobs.process_next(self.handle_job, analysis_id=job_id)
        result = self._repository.get_internal(job_id)
        if result is not None:
            return result
        if job is None:
            raise AnalysisNotFound("Analysis job not found or not claimable")
        if job.status is AnalysisStatus.PENDING:
            raise AnalysisNotReady("Analysis will retry with the same analysis_id")
        if job.status is AnalysisStatus.FAILED:
            raise AIAnalysisError(job.failure_message or "Analysis failed")
        raise AnalysisNotReady("Analysis has not produced a result yet")

    async def handle_job(self, payload: dict[str, Any]) -> str:
        """Generic job-manager handler, with no external client constructed at import."""
        try:
            analysis_id = UUID(payload["analysis_id"])
            request = AnalysisRequest.model_validate(payload["request"])
            candidate = Candidate.model_validate(payload["candidate"])
            profile = AnalysisProfile.model_validate(payload["profile"])
            portfolio_payload = payload.get("portfolio")
            portfolio = (
                PortfolioSnapshotReference.model_validate(portfolio_payload) if portfolio_payload else None
            )
            warnings = list(payload.get("warnings") or [])
        except Exception as exc:
            raise PermanentAnalysisError("Stored analysis request is invalid") from exc

        tokens = bind_log_context(module="ai_analysis", analysis_id=str(analysis_id))
        started_at = self._repository.mark_running(analysis_id)
        try:
            provider_request = AnalysisProviderRequest(
                analysis_id=analysis_id,
                candidate_id=candidate.candidate_id,
                instrument=candidate.instrument,
                analysis_date=request.analysis_date,
                horizon=request.horizon,
                profile=profile,
                portfolio=portfolio,
                warnings=warnings,
            )
            provider_output = await self._provider.analyze(provider_request)
            result = _normalize_result(provider_request, provider_output, started_at)
            self._repository.complete(
                result,
                provider_version=provider_output.provider_version,
                started_at=started_at,
            )
            return f"analysis:{analysis_id}"
        except TransientProviderFailure as exc:
            self._repository.mark_pending(analysis_id)
            raise TransientAnalysisError("Analysis provider failed transiently") from exc
        except PermanentProviderFailure as exc:
            self._repository.mark_failed(analysis_id)
            raise PermanentAnalysisError(str(exc)) from exc
        except Exception as exc:
            self._repository.mark_failed(analysis_id)
            logger.warning("Analysis normalization or persistence failed (%s)", type(exc).__name__)
            raise PermanentAnalysisError("Analysis failed validation or result normalization") from exc
        finally:
            reset_log_context(tokens)

    async def get_analysis(self, analysis_id: UUID, *, owner_id: int) -> AnalysisResult | None:
        return self._repository.get(analysis_id, owner_id=owner_id)

    async def list_analyses(
        self,
        filters: AnalysisFilters,
        *,
        owner_id: int,
    ) -> list[AnalysisResult]:
        return self._repository.list(filters, owner_id=owner_id)

    async def _resolve_portfolio(
        self,
        request: AnalysisRequest,
        profile: AnalysisProfile,
        owner_id: int,
    ) -> tuple[PortfolioSnapshotReference | None, list[str]]:
        warnings: list[str] = []
        if not request.include_portfolio_context:
            if profile.portfolio_context_required:
                raise InvalidAnalysisRequest("The selected profile requires fresh portfolio context")
            return None, ["PORTFOLIO_CONTEXT_NOT_INCLUDED"]
        if self._portfolio_provider is None:
            if profile.portfolio_context_required:
                raise InvalidAnalysisRequest("The selected profile requires an account snapshot provider")
            return None, ["PORTFOLIO_CONTEXT_UNAVAILABLE"]
        try:
            snapshot = await self._portfolio_provider.get_snapshot(owner_id=owner_id)
        except Exception as exc:
            if profile.portfolio_context_required:
                raise InvalidAnalysisRequest("The selected profile requires a fresh portfolio snapshot") from exc
            return None, ["PORTFOLIO_CONTEXT_UNAVAILABLE"]
        if snapshot is None:
            if profile.portfolio_context_required:
                raise InvalidAnalysisRequest("The selected profile requires a fresh portfolio snapshot")
            return None, ["PORTFOLIO_CONTEXT_UNAVAILABLE"]
        age_seconds = (datetime.now(timezone.utc) - snapshot.captured_at.astimezone(timezone.utc)).total_seconds()
        if age_seconds < -30 or age_seconds > profile.max_portfolio_age_seconds:
            if profile.portfolio_context_required:
                raise InvalidAnalysisRequest("The selected profile requires a fresh portfolio snapshot")
            return None, ["PORTFOLIO_CONTEXT_STALE"]
        return snapshot, warnings


def _request_profile_overrides(profile: AnalysisProfile, request: AnalysisRequest) -> AnalysisProfile:
    analysts = tuple(item.strip().lower() for item in request.selected_analysts) or profile.selected_analysts
    try:
        return AnalysisProfile.model_validate(
            profile.model_dump(mode="python")
            | {
                "selected_analysts": analysts,
                "checkpoint_enabled": request.checkpoint_enabled,
                "save_html_report": request.save_html_report,
            }
        )
    except Exception as exc:
        raise InvalidAnalysisRequest("Selected analysts or run options are invalid for this provider") from exc


def _run_config_snapshot(
    request: AnalysisRequest,
    profile: AnalysisProfile,
    portfolio_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "provider": request.provider.value,
        "analysis_date": request.analysis_date.isoformat(),
        "horizon": request.horizon.value,
        "profile": profile.model_dump(mode="json"),
        "portfolio_snapshot_id": portfolio_payload.get("snapshot_id") if portfolio_payload else None,
        "portfolio_captured_at": portfolio_payload.get("captured_at") if portfolio_payload else None,
    }


def _normalize_result(
    request: AnalysisProviderRequest,
    output: AnalysisProviderOutput,
    started_at: datetime,
) -> AnalysisResult:
    raw_rating = output.source_rating
    direction = AnalysisDirection(normalize_direction(raw_rating))
    warnings = list(request.warnings) + list(output.warnings)
    if direction is AnalysisDirection.REVIEW and "UPSTREAM_RATING_REVIEW" not in warnings:
        warnings.append("UPSTREAM_RATING_REVIEW")
    reports = {
        str(name): text.strip()
        for name, text in output.reports.items()
        if isinstance(name, str) and isinstance(text, str) and text.strip()
    }
    return AnalysisResult(
        analysis_id=request.analysis_id,
        candidate_id=request.candidate_id,
        symbol=request.instrument.symbol,
        analysis_ticker=request.instrument.analysis_ticker or request.instrument.symbol,
        provider=ProviderName.TRADING_AGENTS,
        provider_version=output.provider_version,
        profile_key=request.profile.key,
        profile_version=request.profile.version,
        analysis_date=request.analysis_date,
        horizon=request.horizon,
        selected_analysts=list(request.profile.selected_analysts),
        quick_provider=request.profile.quick_provider,
        quick_model=request.profile.quick_model,
        deep_provider=request.profile.deep_provider,
        deep_model=request.profile.deep_model,
        portfolio_snapshot_id=request.portfolio.snapshot_id if request.portfolio else None,
        status=AnalysisStatus.COMPLETED,
        source_rating=raw_rating,
        direction=direction,
        reports=reports,
        warnings=warnings,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        report_artifacts=output.report_artifacts,
    )
