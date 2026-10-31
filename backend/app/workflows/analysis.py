"""Cross-module orchestration for selecting a candidate for analysis."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.shared.contracts import AnalysisJobReceipt, AnalysisRequest, Candidate
from app.shared.logging import bind_log_context, reset_log_context


class CandidateService(Protocol):
    async def get_candidate(self, candidate_id: UUID, *, owner_id: int | None = None) -> Candidate: ...


class AnalysisRequestService(Protocol):
    async def request_analysis(
        self,
        request: AnalysisRequest,
        *,
        owner_id: int,
        idempotency_key: str,
    ) -> AnalysisJobReceipt: ...


class CandidateNotReadyForAnalysis(ValueError):
    """Candidate does not have an analysis ticker resolved by Stock Selection."""


class StockSelectionAnalysisWorkflow:
    """Validate Module 1 output before requesting a durable Module 2 analysis."""

    def __init__(self, candidates: CandidateService, analyses: AnalysisRequestService):
        self._candidates = candidates
        self._analyses = analyses

    async def request_candidate_analysis(
        self,
        candidate_id: UUID,
        request: AnalysisRequest,
        *,
        owner_id: int,
        idempotency_key: str,
    ) -> AnalysisJobReceipt:
        if request.candidate_id != candidate_id:
            raise ValueError("analysis request candidate_id does not match the selected candidate")
        candidate = await self._candidates.get_candidate(candidate_id, owner_id=owner_id)
        ticker = candidate.instrument.analysis_ticker
        if ticker is None or not ticker.strip():
            raise CandidateNotReadyForAnalysis("candidate has no resolved analysis ticker")

        tokens = bind_log_context(module="workflows", analysis_candidate_id=str(candidate_id))
        try:
            return await self._analyses.request_analysis(
                request,
                owner_id=owner_id,
                idempotency_key=idempotency_key,
            )
        finally:
            reset_log_context(tokens)


__all__ = ["CandidateNotReadyForAnalysis", "StockSelectionAnalysisWorkflow"]
