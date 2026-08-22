"""
Agent 2 — Email Service Unit & Integration Tests (Dry-Run Mode)

Tests:
1. validate_recipient rejects addresses outside org_directory.json (Rule #6).
2. All 6 Jinja2 templates render cleanly without syntax/variable errors.
3. Dry-run email dispatch completes with status="DRY_RUN".
4. Intelligent email drafting returns structured {subject, body, priority} object.
"""

import pytest

from app.agents.agent2_execution.communication.schemas import EmailRequest
from app.agents.agent2_execution.config import settings
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.tools.email_service import EmailService, IntelligentEmailDraft


@pytest.fixture
def email_service():
    """Returns an EmailService instance in dry-run mode."""
    # Ensure dry run is active
    settings.EMAIL_DRY_RUN = True
    return EmailService(session=None)


# ---------------------------------------------------------------------------
# 1. Recipient Validation Tests (Rule #6)
# ---------------------------------------------------------------------------

def test_validate_recipient_allowed_org_user(email_service):
    is_valid, reason = email_service.validate_recipient("alice.johnson@acmeglobal.com", "requester")
    assert is_valid is True
    assert "authorized" in reason.lower()

    is_valid_mgr, _ = email_service.validate_recipient("frank.miller@acmeglobal.com", "manager")
    assert is_valid_mgr is True


def test_validate_recipient_unauthorized_external(email_service):
    is_valid, reason = email_service.validate_recipient("attacker@external-domain.com", "unknown")
    assert is_valid is False
    assert "not in the allowed organizational directory" in reason


def test_validate_recipient_empty(email_service):
    is_valid, reason = email_service.validate_recipient("", "requester")
    assert is_valid is False
    assert "cannot be empty" in reason.lower()


# ---------------------------------------------------------------------------
# 2. Jinja2 Template Rendering Tests (All 6 Templates)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "template_name",
    [
        "task_assignment.html",
        "reminder.html",
        "sla_warning.html",
        "escalation.html",
        "exception.html",
        "completion.html",
    ],
)
def test_all_6_templates_render_cleanly(email_service, template_name):
    context = {
        "subject": "Test Email Subject",
        "body": "This is a test notification body for procurement process.",
        "process_id": "proc-1001",
        "task_id": "task-2002",
        "recipient_role": "manager",
        "elapsed_hours": 18.5,
        "sla_hours": 24.0,
        "severity": "HIGH",
    }
    rendered_html = email_service.render_template(template_name, context)
    assert isinstance(rendered_html, str)
    assert "Test Email Subject" in rendered_html
    assert "proc-1001" in rendered_html
    assert "<html>" in rendered_html.lower()


# ---------------------------------------------------------------------------
# 3. Dry-Run Dispatch Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_email_dry_run(email_service):
    req = EmailRequest(
        recipient="frank.miller@acmeglobal.com",
        subject="Approval Required: Purchase Request #1001",
        body="Please review purchase request #1001.",
        priority="HIGH",
        process_id="proc-1001",
        task_id="task-500",
        recipient_role="manager",
        template_name="task_assignment.html",
    )
    result = await email_service.send_email(req)
    assert result.status == "DRY_RUN"
    assert result.message_id.startswith("msg-")
    assert result.error == ""


# ---------------------------------------------------------------------------
# 4. Intelligent Email Content Drafting Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_draft_intelligent_email(email_service):
    gemini_stub_client = GeminiClient(is_offline=True)
    context = {
        "recipient_role": "manager",
        "purpose": "Manager SLA Reminder",
        "process_id": "proc-9901",
        "current_state": "PENDING_APPROVAL",
        "elapsed_hours": 19.5,
        "sla_hours": 24.0,
    }
    draft = await email_service.draft_intelligent_email(context, gemini_client=gemini_stub_client)
    assert isinstance(draft, IntelligentEmailDraft)
    assert draft.subject != ""
    assert draft.body != ""
    assert draft.priority in ["LOW", "MEDIUM", "HIGH", "URGENT"]
