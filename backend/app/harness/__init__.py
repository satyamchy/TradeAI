"""Single-application automation and scheduling harness."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.trading.automation_runner import AutomationRunner


def get_automation_runner() -> "AutomationRunner":
    """Return the one existing runner instance without starting it."""
    from app.trading.automation_runner import automation_runner

    return automation_runner
