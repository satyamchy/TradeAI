"""Typed public interface for stock selection; implementations are added in Phase 2."""

from typing import Protocol

from app.modules.stock_selection.schemas import CandidateBatch, CreateCandidatesRequest


class StockSelectionService(Protocol):
    """Create a validated, typed batch of candidate instruments."""

    async def create_candidates(self, request: CreateCandidatesRequest) -> CandidateBatch:
        """Return a batch with valid candidates and per-symbol rejections."""
        ...
