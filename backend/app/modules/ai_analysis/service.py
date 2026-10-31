"""Typed public interface for AI analysis; no provider is loaded at import time."""

from typing import Protocol

from app.shared.contracts import AnalysisJobReceipt, AnalysisRequest


class AIAnalysisService(Protocol):
    """Submit analysis to the job service and retrieve normalized results."""

    async def submit(self, request: AnalysisRequest, *, idempotency_key: str) -> AnalysisJobReceipt:
        """Persist or return the job with the same idempotency key."""
        ...
