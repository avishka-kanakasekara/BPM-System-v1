"""G10 — production guard and hardening tests."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.agents.agent2_execution.security.trace_sanitizer import sanitize_execution_explanation
from app.core.config import Settings
from app.core.logging import JsonFormatter, correlation_id_var
from app.core.rate_limit import RateLimitExceeded, SlidingWindowRateLimiter
from app.core.redaction import redact_text
from app.main import app


def test_production_rejects_mock_llm():
    cfg = Settings(
        ENV="production",
        SUPABASE_URL="https://example.supabase.co",
        GEMINI_API_KEY="real-key",
        MOCK_LLM=True,
        GEMINI_OFFLINE=False,
        DEBUG=False,
        EMAIL_DRY_RUN=False,
        EMAIL_PROVIDER="resend",
        EMAIL_API_KEY="re_key",
        EMAIL_FROM="noreply@example.com",
        CORS_ORIGINS=["https://app.example.com"],
    )
    with pytest.raises(RuntimeError, match="MOCK_LLM"):
        cfg.assert_production_config()


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValueError, match="CORS_ORIGINS cannot include"):
        Settings(
            ENV="production",
            SUPABASE_URL="https://x.supabase.co",
            CORS_ORIGINS=["*"],
        )


def test_correlation_id_header_on_requests():
    client = TestClient(app)
    response = client.get("/health/live", headers={"X-Correlation-ID": "corr-test-123"})
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") == "corr-test-123"


def test_health_demo_lists_migration_0024_without_secrets():
    client = TestClient(app)
    response = client.get("/health/demo")
    assert response.status_code == 200
    body = response.json()
    assert body["migration_0024_on_disk"] is True
    assert any(name.startswith("0024") for name in body["migrations_on_disk"])
    blob = json.dumps(body)
    assert "service_role" not in blob.lower()
    assert "eyJ" not in blob
    assert "sk-" not in blob


def test_rate_limiter_blocks_burst():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
    limiter.check("k")
    limiter.check("k")
    with pytest.raises(RateLimitExceeded):
        limiter.check("k")


def test_json_logs_redact_known_secret():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="auth failed api_key=super-secret-value-12345",
        args=(),
        exc_info=None,
    )
    token = correlation_id_var.set("corr-abc")
    try:
        line = formatter.format(record)
    finally:
        correlation_id_var.reset(token)
    payload = json.loads(line)
    assert payload["correlation_id"] == "corr-abc"
    assert "super-secret-value-12345" not in line
    assert "[REDACTED]" in payload["message"]


def test_trace_sanitizer_never_leaks_bearer_token():
    raw = {
        "decision_reason": "Used Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig",
        "plan_reasoning": "api_key=abc123",
        "execution_events": [],
    }
    safe = sanitize_execution_explanation(raw)
    serialized = json.dumps(safe)
    assert "eyJhbGciOiJIUzI1NiJ9" not in serialized
    assert "abc123" not in serialized
    assert "Bearer" not in safe["plan_summary"]


def test_redact_text_covers_service_role_pattern():
    text = "service_role_key=eyJsecretpart"
    assert "eyJsecretpart" not in redact_text(text)
