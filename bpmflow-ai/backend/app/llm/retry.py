"""Shared LLM retry / transient-error detection for all agents."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

TRANSIENT_EXCEPTION_NAMES = frozenset(
    {
        "RateLimitError",
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "OverloadedError",
        "ServiceUnavailableError",
    }
)

TRANSIENT_HTTP_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504, 529})


def is_transient_llm_error(exc: BaseException) -> bool:
    """Return True when an LLM provider error is worth retrying."""
    if type(exc).__name__ in TRANSIENT_EXCEPTION_NAMES:
        return True
    status = getattr(exc, "status_code", None)
    if status in TRANSIENT_HTTP_STATUSES:
        return True
    text = str(exc)
    if "RESOURCE_EXHAUSTED" in text or "429" in text:
        return True
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


def call_with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    initial_backoff_seconds: float = 0.5,
    is_transient: Callable[[BaseException], bool] | None = None,
) -> T:
    """Invoke ``fn`` with exponential backoff on transient failures."""
    checker = is_transient or is_transient_llm_error
    delay = initial_backoff_seconds
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except BaseException as exc:
            last_exc = exc
            if attempt >= max_attempts - 1 or not checker(exc):
                raise
            time.sleep(delay)
            delay *= 2
    assert last_exc is not None
    raise last_exc
