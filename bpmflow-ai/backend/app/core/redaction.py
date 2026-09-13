"""PII and secret redaction for logs, traces, and API payloads."""

from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(api[_-]?key|secret|token|password|authorization)\s*[:=]\s*\S+", re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I),
    re.compile(r"sk-[A-Za-z0-9]{10,}", re.I),
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWT shape
    re.compile(r"service_role[_-]?key\s*[:=]\s*\S+", re.I),
)

_REDACTED = "[REDACTED]"


def redact_text(value: str) -> str:
    """Replace known secret patterns in a string."""
    if not value:
        return value
    out = value
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(_REDACTED, out)
    return out


def redact_value(value: Any) -> Any:
    """Recursively redact secrets in strings inside mappings and sequences."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_key(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    return value


def _redact_key(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(token in lowered for token in ("password", "secret", "token", "api_key", "authorization")):
        if value is None:
            return None
        return _REDACTED
    return redact_value(value)


def contains_unredacted_secret(text: str, *, needle: str) -> bool:
    """Return True if ``needle`` appears literally (test helper)."""
    return needle in text and _REDACTED not in text.replace(needle, "")
