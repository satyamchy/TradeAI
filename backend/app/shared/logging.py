"""Shared structured logging and request/entity correlation context."""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
analysis_id_context: ContextVar[str | None] = ContextVar("analysis_id", default=None)
decision_id_context: ContextVar[str | None] = ContextVar("decision_id", default=None)
module_context: ContextVar[str | None] = ContextVar("module", default=None)

_SENSITIVE_VALUE = re.compile(
    r"(?i)([a-z0-9_-]*(?:token|client[_ -]?id|api[_ -]?(?:key|secret)|password|secret|authorization|credential|private[_ -]?key)[a-z0-9_-]*)\s*[:=]\s*([^\s,;]+)"
)


def _redact(value: str) -> str:
    return _SENSITIVE_VALUE.sub(r"\1=[REDACTED]", value)


class StructuredFormatter(logging.Formatter):
    """Emit one JSON object per line with the current correlation identifiers."""

    def format(self, record: logging.LogRecord) -> str:
        message = _redact(record.getMessage())
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        for name, context in (
            ("request_id", request_id_context),
            ("analysis_id", analysis_id_context),
            ("decision_id", decision_id_context),
            ("module", module_context),
        ):
            value = context.get()
            if value:
                payload[name] = value
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure a single application-wide structured handler once."""
    root = logging.getLogger()
    if not any(getattr(handler, "_tradex_structured", False) for handler in root.handlers):
        formatter = StructuredFormatter()
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler._tradex_structured = True  # type: ignore[attr-defined]
        root.addHandler(console_handler)

        log_dir = Path(__file__).resolve().parents[2] / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "tradex.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler._tradex_structured = True  # type: ignore[attr-defined]
        root.addHandler(file_handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger wired to the common redacting structured formatter."""
    configure_logging()
    return logging.getLogger(name)


def bind_log_context(**values: str | None) -> dict[str, object]:
    """Set any supported context fields and return tokens for later reset."""
    tokens: dict[str, object] = {}
    contexts = {
        "request_id": request_id_context,
        "analysis_id": analysis_id_context,
        "decision_id": decision_id_context,
        "module": module_context,
    }
    for name, value in values.items():
        context = contexts.get(name)
        if context is not None:
            tokens[name] = context.set(value)
    return tokens


def reset_log_context(tokens: dict[str, object]) -> None:
    """Reset fields previously bound with `bind_log_context`."""
    contexts = {
        "request_id": request_id_context,
        "analysis_id": analysis_id_context,
        "decision_id": decision_id_context,
        "module": module_context,
    }
    for name, token in tokens.items():
        context = contexts.get(name)
        if context is not None:
            context.reset(token)  # type: ignore[arg-type]
