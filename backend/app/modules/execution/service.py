"""Typed public interface for broker-neutral execution."""

from typing import Protocol

from app.modules.execution.schemas import ExecutionResult
from app.shared.contracts import ApprovedOrderIntent


class ExecutionService(Protocol):
    """Validate and idempotently execute an approved persisted intent."""

    async def execute(self, intent: ApprovedOrderIntent) -> ExecutionResult:
        """Submit an approved intent and return normalized broker state."""
        ...
