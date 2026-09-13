"""Health endpoint tests — live vs ready vs dependency probes."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_live_always_200(client) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "alive"


def test_health_deps_reports_degraded_when_all_down(client, monkeypatch) -> None:
    from app.core.health import ProbeResult
    from app.core.persistence.policy import PersistenceMode

    monkeypatch.setattr("app.core.persistence.repository._postgres_reachable", lambda: False)
    monkeypatch.setattr("app.core.persistence.repository._rest_reachable", lambda: False)
    monkeypatch.setattr("app.core.config.settings.SUPABASE_URL", None)
    monkeypatch.setattr("app.core.config.settings.SUPABASE_JWT_SECRET", None)
    monkeypatch.setattr(
        "app.core.health.probe_and_update_status",
        lambda: PersistenceMode.UNAVAILABLE,
    )

    async def _pg_down():
        return ProbeResult(name="postgres", status="error", latency_ms=1.0)

    async def _rest_down():
        return ProbeResult(name="supabase_rest", status="error", latency_ms=1.0)

    async def _jwks_down():
        return ProbeResult(name="jwks", status="error", latency_ms=1.0)

    async def _gemini_skip():
        return ProbeResult(name="gemini", status="skipped", latency_ms=0.0)

    async def _redis_skip():
        return ProbeResult(name="redis", status="skipped", latency_ms=0.0)

    with patch("app.core.health.probe_postgres", _pg_down), patch(
        "app.core.health.probe_supabase_rest", _rest_down
    ), patch("app.core.health.probe_jwks", _jwks_down), patch(
        "app.core.health.probe_gemini", _gemini_skip
    ), patch(
        "app.core.health.probe_redis", _redis_skip
    ):
        response = client.get("/health/deps")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["ready"] is False
    assert body["persistence_mode"] == "unavailable"


def test_health_ready_503_when_postgres_and_rest_down(client, monkeypatch) -> None:
    from app.core.health import ProbeResult
    from app.core.persistence.policy import PersistenceMode

    monkeypatch.setattr("app.core.persistence.repository._postgres_reachable", lambda: False)
    monkeypatch.setattr("app.core.persistence.repository._rest_reachable", lambda: False)
    monkeypatch.setattr(
        "app.core.health.probe_and_update_status",
        lambda: PersistenceMode.UNAVAILABLE,
    )

    async def _pg_down():
        return ProbeResult(name="postgres", status="error", latency_ms=1.0)

    async def _rest_down():
        return ProbeResult(name="supabase_rest", status="error", latency_ms=1.0)

    async def _jwks_skip():
        return ProbeResult(name="jwks", status="skipped", latency_ms=0.0)

    async def _gemini_skip():
        return ProbeResult(name="gemini", status="skipped", latency_ms=0.0)

    async def _redis_skip():
        return ProbeResult(name="redis", status="skipped", latency_ms=0.0)

    with patch("app.core.health.probe_postgres", _pg_down), patch(
        "app.core.health.probe_supabase_rest", _rest_down
    ), patch("app.core.health.probe_jwks", _jwks_skip), patch(
        "app.core.health.probe_gemini", _gemini_skip
    ), patch(
        "app.core.health.probe_redis", _redis_skip
    ):
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_health_deps_ok_when_rest_up(client, monkeypatch) -> None:
    from app.core.health import ProbeResult

    monkeypatch.setattr("app.core.persistence.repository._postgres_reachable", lambda: False)
    monkeypatch.setattr("app.core.persistence.repository._rest_reachable", lambda: True)
    monkeypatch.setattr("app.core.config.settings.SUPABASE_JWT_SECRET", "test-secret")

    async def _pg_down():
        return ProbeResult(name="postgres", status="error", latency_ms=1.0)

    async def _rest_up():
        return ProbeResult(name="supabase_rest", status="ok", latency_ms=1.0)

    async def _jwks_skip():
        return ProbeResult(name="jwks", status="skipped", latency_ms=0.0)

    async def _gemini_skip():
        return ProbeResult(name="gemini", status="skipped", latency_ms=0.0)

    async def _redis_skip():
        return ProbeResult(name="redis", status="skipped", latency_ms=0.0)

    with patch("app.core.health.probe_postgres", _pg_down), patch(
        "app.core.health.probe_supabase_rest", _rest_up
    ), patch("app.core.health.probe_jwks", _jwks_skip), patch(
        "app.core.health.probe_gemini", _gemini_skip
    ), patch(
        "app.core.health.probe_redis", _redis_skip
    ):
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["persistence"]["degraded"] is True
    assert body["persistence_mode"] == "rest"
