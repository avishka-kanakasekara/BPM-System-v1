"""Structured JSON logging for the API and future audit events."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.redaction import redact_text, redact_value

# Propagated by CorrelationMiddleware on every request.
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
# Back-compat alias used by older modules.
trace_id_var = correlation_id_var


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
    """Emit one JSON object per log line with correlation_id and redaction."""

    def format(self, record: logging.LogRecord) -> str:
        correlation_id = (
            getattr(record, "correlation_id", None)
            or correlation_id_var.get()
            or getattr(record, "trace_id", None)
        )
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "correlation_id": correlation_id,
            "message": redact_text(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key in payload or key in _RESERVED_LOG_ATTRS or key.startswith("_"):
                continue
            payload[key] = redact_value(value)
        upload_filename = getattr(record, "upload_filename", None)
        if upload_filename is not None:
            payload["filename"] = upload_filename
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


class CorrelationFilter(logging.Filter):
    """Attach correlation_id to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "correlation_id", None):
            record.correlation_id = correlation_id_var.get()
        if not getattr(record, "trace_id", None):
            record.trace_id = correlation_id_var.get()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(CorrelationFilter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
