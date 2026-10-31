"""Typed public interface for position evaluation and exit candidates."""

from typing import Protocol

from app.modules.position_monitoring.schemas import PositionEvaluation, PositionSnapshot


class PositionMonitoringService(Protocol):
    """Evaluate confirmed positions without submitting broker orders."""

    def evaluate(self, position: PositionSnapshot) -> PositionEvaluation:
        """Return a hold, reassessment, exit-candidate, or data-unavailable view."""
        ...
