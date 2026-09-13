"""Shared HTTP clients with timeouts and circuit breaking."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import httpx

from app.core.circuit_breaker import get_circuit_breaker
from app.core.config import settings

T = TypeVar("T")


def external_timeout_seconds() -> float:
    return float(settings.EXTERNAL_HTTP_TIMEOUT_SECONDS)


def sync_client(*, timeout: float | None = None, trust_env: bool = False) -> httpx.Client:
    return httpx.Client(timeout=timeout or external_timeout_seconds(), trust_env=trust_env)


def async_client(*, timeout: float | None = None, trust_env: bool = False) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout or external_timeout_seconds(), trust_env=trust_env)


def call_with_circuit(dependency: str, fn: Callable[[], T]) -> T:
    """Run ``fn`` guarded by a named circuit breaker."""
    breaker = get_circuit_breaker(dependency)
    breaker.before_call()
    try:
        result = fn()
    except Exception:
        breaker.record_failure()
        raise
    breaker.record_success()
    return result
