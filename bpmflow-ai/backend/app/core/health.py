"""Dependency health probes with timeouts."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.core.persistence import persistence_status, probe_and_update_status

logger = get_logger(__name__)


@dataclass(frozen=True)
class ProbeResult:
    name: str
    status: str  # ok | degraded | error | skipped
    latency_ms: float
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 1),
        }
        if self.detail:
            payload["detail"] = self.detail
        return payload


async def _run_probe(name: str, fn: Callable[[], bool | Coroutine[Any, Any, bool]]) -> ProbeResult:
    started = time.perf_counter()
    try:
        result = fn()
        if asyncio.iscoroutine(result):
            ok = await asyncio.wait_for(result, timeout=settings.HEALTH_PROBE_TIMEOUT_SECONDS)
        else:
            ok = result
        latency = (time.perf_counter() - started) * 1000
        return ProbeResult(
            name=name,
            status="ok" if ok else "error",
            latency_ms=latency,
            detail=None if ok else "probe returned false",
        )
    except TimeoutError:
        latency = (time.perf_counter() - started) * 1000
        return ProbeResult(name=name, status="error", latency_ms=latency, detail="timeout")
    except Exception as exc:
        latency = (time.perf_counter() - started) * 1000
        logger.warning("health_probe_failed", extra={"probe": name, "error": str(exc)})
        return ProbeResult(
            name=name,
            status="error",
            latency_ms=latency,
            detail=f"{type(exc).__name__}",
        )


async def probe_postgres() -> ProbeResult:
    from app.core.database import probe_postgres_sync

    return await _run_probe(
        "postgres",
        lambda: probe_postgres_sync(timeout_seconds=settings.HEALTH_PROBE_TIMEOUT_SECONDS),
    )


async def probe_supabase_rest() -> ProbeResult:
    from app.core.supabase_rest import ping_rest, supabase_rest_configured

    if not supabase_rest_configured():
        return ProbeResult(name="supabase_rest", status="skipped", latency_ms=0.0, detail="not configured")
    return await _run_probe(
        "supabase_rest",
        lambda: ping_rest(timeout_seconds=settings.HEALTH_PROBE_TIMEOUT_SECONDS),
    )


async def probe_jwks() -> ProbeResult:
    if not settings.SUPABASE_URL:
        if settings.SUPABASE_JWT_SECRET:
            return ProbeResult(name="jwks", status="skipped", latency_ms=0.0, detail="using HS256 secret")
        return ProbeResult(name="jwks", status="error", latency_ms=0.0, detail="not configured")

    from app.core.security import fetch_jwks

    async def _fetch() -> bool:
        payload = await fetch_jwks()
        return bool(payload.get("keys"))

    return await _run_probe("jwks", _fetch)


async def probe_gemini() -> ProbeResult:
    if settings.MOCK_LLM or settings.GEMINI_OFFLINE:
        return ProbeResult(name="gemini", status="skipped", latency_ms=0.0, detail="mock/offline mode")
    if not (settings.GEMINI_API_KEY or "").strip():
        return ProbeResult(name="gemini", status="skipped", latency_ms=0.0, detail="not configured")
    return ProbeResult(name="gemini", status="ok", latency_ms=0.0, detail="configured")


async def probe_redis() -> ProbeResult:
    url = (settings.REDIS_URL or "").strip()
    if not url:
        return ProbeResult(name="redis", status="skipped", latency_ms=0.0, detail="not configured")

    async def _ping() -> bool:
        import redis.asyncio as redis

        client = redis.from_url(url, socket_connect_timeout=settings.HEALTH_PROBE_TIMEOUT_SECONDS)
        try:
            return bool(await client.ping())
        finally:
            await client.aclose()

    return await _run_probe("redis", _ping)


async def run_dependency_probes() -> dict[str, Any]:
    """Run all probes and refresh persistence status."""
    mode = await asyncio.to_thread(probe_and_update_status)
    probes = await asyncio.gather(
        probe_postgres(),
        probe_supabase_rest(),
        probe_jwks(),
        probe_gemini(),
        probe_redis(),
    )
    probe_map = {p.name: p.as_dict() for p in probes}
    persistence = persistence_status.snapshot()

    critical_ok = (
        probe_map.get("postgres", {}).get("status") == "ok"
        or probe_map.get("supabase_rest", {}).get("status") == "ok"
    )
    auth_ok = probe_map.get("jwks", {}).get("status") in {"ok", "skipped"}

    return {
        "persistence_mode": mode.value,
        "persistence": persistence,
        "probes": probe_map,
        "ready": critical_ok and auth_ok,
    }


def live_payload() -> dict[str, Any]:
    return {"status": "alive", "env": settings.ENV}


async def ready_payload() -> dict[str, Any]:
    report = await run_dependency_probes()
    status = "ready" if report["ready"] else "not_ready"
    return {"status": status, **report}
