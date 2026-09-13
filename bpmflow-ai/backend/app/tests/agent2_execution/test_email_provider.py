"""
Agent 2 — Email provider tests (dry-run and unconfigured failure paths).
"""

import pytest

from app.agents.agent2_execution.config import settings
from app.agents.agent2_execution.tools.email_provider import dispatch_email, email_configured


@pytest.mark.asyncio
async def test_dispatch_email_dry_run():
    settings.EMAIL_DRY_RUN = True
    result = await dispatch_email(
        recipient="frank.miller@acmeglobal.com",
        subject="Test",
        body_plain="Body",
        body_html="<p>Body</p>",
        idempotency_key="test-key-1",
    )
    assert result.success is True
    assert result.status == "DRY_RUN"
    assert result.message_id.startswith("dry-")


@pytest.mark.asyncio
async def test_dispatch_email_unconfigured_fails_clearly(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_DRY_RUN", False)
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "EMAIL_API_KEY", "")
    monkeypatch.setattr(settings, "EMAIL_FROM", "")
    assert email_configured() is False
    result = await dispatch_email(
        recipient="frank.miller@acmeglobal.com",
        subject="Test",
        body_plain="Body",
        body_html="<p>Body</p>",
    )
    assert result.success is False
    assert result.status == "FAILED"
    assert "not configured" in result.error.lower()
