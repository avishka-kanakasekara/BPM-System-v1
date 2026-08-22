"""Structured JSON logging for the API and future audit events."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

# Filled by request middleware later; remains None until audit tracing is wired.
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


_RESERVED_LOG_ATTRS = {
    "name",
    "msg",
    "args",
    "created",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "exc_info",
    "exc_text",
    "thread",
    "threadName",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "trace_id": getattr(record, "trace_id", None) or trace_id_var.get(),
            "message": record.getMessage(),
        }
        # Preserve structured extras (ingestion audit fields, later LLM traces).
        for key, value in record.__dict__.items():
            if key in payload or key in _RESERVED_LOG_ATTRS or key.startswith("_"):
                continue
            payload[key] = value
        if getattr(record, "upload_filename", None) is not None:
            payload["filename"] = record.upload_filename
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TraceIdFilter(logging.Filter):
    """Attach the current trace_id placeholder to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "trace_id", None):
            record.trace_id = trace_id_var.get()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(TraceIdFilter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Keep uvicorn access logs human-readable enough via the same JSON shape.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
