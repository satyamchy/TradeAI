"""Compatibility facade for the shared structured logger."""

from app.shared.logging import configure_logging, get_logger

__all__ = ["configure_logging", "get_logger"]
