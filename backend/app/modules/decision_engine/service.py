"""Typed public interface for deterministic, AI-provider-neutral decisions."""

from typing import Protocol

from app.modules.decision_engine.schemas import DecisionResult, EvaluateTradeRequest


class DecisionEngineService(Protocol):
    """Evaluate approved inputs using TradeX-owned strategies and risk rules."""

    def evaluate_entry(self, request: EvaluateTradeRequest) -> DecisionResult:
        """Return a decision and an approved intent only when all checks pass."""
        ...

    def evaluate_exit(self, request: EvaluateTradeRequest) -> DecisionResult:
        """Evaluate an exit independently of any AI provider implementation."""
        ...
