"""Cross-module orchestration from normalized analysis to a decision."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.decision_engine.schemas import DecisionResult
from app.shared.contracts import AnalysisResult, AnalysisStatus, EvaluateTradeRequest
from app.shared.logging import bind_log_context, reset_log_context


class AnalysisResultService(Protocol):
    async def get_analysis(self, analysis_id: UUID, *, owner_id: int) -> AnalysisResult | None: ...


class EntryDecisionService(Protocol):
    async def evaluate_entry(self, request: EvaluateTradeRequest, *, owner_id: int) -> DecisionResult: ...


class AnalysisUnavailable(ValueError):
    """The requested owner-scoped analysis result is not available."""


class AnalysisDecisionWorkflow:
    """Load a completed result and delegate all signal/risk rules to Module 3."""

    def __init__(self, analyses: AnalysisResultService, decisions: EntryDecisionService):
        self._analyses = analyses
        self._decisions = decisions

    async def evaluate_entry(
        self,
        analysis_id: UUID,
        *,
        owner_id: int,
        strategy_key: str,
    ) -> DecisionResult:
        analysis = await self._analyses.get_analysis(analysis_id, owner_id=owner_id)
        if analysis is None or analysis.status is not AnalysisStatus.COMPLETED:
            raise AnalysisUnavailable("completed analysis was not found")
        tokens = bind_log_context(
            module="workflows",
            analysis_id=str(analysis_id),
            decision_strategy=strategy_key,
        )
        try:
            return await self._decisions.evaluate_entry(
                EvaluateTradeRequest(analysis_id=analysis_id, strategy_key=strategy_key),
                owner_id=owner_id,
            )
        finally:
            reset_log_context(tokens)


__all__ = ["AnalysisDecisionWorkflow", "AnalysisUnavailable"]
