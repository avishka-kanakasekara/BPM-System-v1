"""
Agent 2 production-readiness tests — authorization, idempotency, email, PO validation.
"""

import uuid
from datetime import UTC
from unittest.mock import AsyncMock

import pytest

from app.agents.agent2_execution.config import settings as agent2_settings
from app.agents.agent2_execution.execution.idempotency import (
    SIDE_EFFECT_TOOLS,
    generate_idempotency_key,
)
from app.agents.agent2_execution.security.execution_authorization import (
    authorize_retry,
    authorize_tool_execution,
)
from app.agents.agent2_execution.security.trace_sanitizer import sanitize_execution_explanation
from app.agents.agent2_execution.tools.email_provider import dispatch_email
from app.agents.agent2_execution.tools.procurement_tools import _compute_po_totals, create_po_draft
from app.agents.agent2_execution.tools.schemas import CreatePODraftInput, POLineItem
from app.agents.agent4_orchestrator.constants import WorkflowStage
from app.core.config import settings as core_settings


@pytest.mark.asyncio
async def test_mutating_tool_requires_workflow_execution_stage():
    process_id = str(uuid.uuid4())

    class FakeProcess:
        current_stage = WorkflowStage.DRAFT

    repo = AsyncMock()
    repo.get_process = AsyncMock(return_value=FakeProcess())
    result = await authorize_tool_execution(repo, process_id, "send_email")
    assert result.authorized is False
    assert result.error_code == "NOT_AUTHORIZED"


@pytest.mark.asyncio
async def test_read_only_tool_allowed_at_any_stage():
    process_id = str(uuid.uuid4())

    class FakeProcess:
        current_stage = WorkflowStage.DRAFT

    repo = AsyncMock()
    repo.get_process = AsyncMock(return_value=FakeProcess())
    result = await authorize_tool_execution(repo, process_id, "calculate_kpi")
    assert result.authorized is True


@pytest.mark.asyncio
async def test_retry_rejects_successful_receipt():
    from datetime import datetime

    from app.agents.agent2_execution.database.models import ExecutionReceipt

    process_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    receipt_id = str(uuid.uuid4())

    class FakeProcess:
        current_stage = WorkflowStage.WORKFLOW_EXECUTION

    repo = AsyncMock()
    repo.get_process = AsyncMock(return_value=FakeProcess())

    original = ExecutionReceipt(
        id=uuid.UUID(receipt_id),
        process_id=uuid.UUID(process_id),
        task_id=uuid.UUID(task_id),
        agent_id="agent_2",
        tool_name="send_email",
        action="send_email",
        attempt_number=1,
        idempotency_key="k",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        status="SUCCESS",
        latency_ms=1,
    )
    from unittest.mock import MagicMock

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = original
    session.execute = AsyncMock(return_value=mock_result)

    result = await authorize_retry(
        repo,
        session,
        receipt_id=receipt_id,
        process_id=process_id,
        task_id=task_id,
        tool_name="send_email",
    )
    assert result.authorized is False
    assert result.error_code == "ALREADY_SUCCEEDED"


def test_po_totals_computed_server_side():
    inp = CreatePODraftInput(
        vendor_id="VENDOR-1",
        process_id=str(uuid.uuid4()),
        items=[
            POLineItem(description="Chair", quantity=2, unit_price=100.0),
            POLineItem(description="Desk", quantity=1, unit_price=250.0),
        ],
        amount=99999.0,
        tax_rate=0.1,
    )
    sub, tax, total = _compute_po_totals(inp)
    assert sub == 450.0
    assert tax == 45.0
    assert total == 495.0


@pytest.mark.asyncio
async def test_create_po_draft_status_is_always_draft():
    from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID
    from app.procurement.schemas import CreateVendorInput
    from app.procurement.service import get_procurement

    get_procurement().create_vendor(
        CreateVendorInput(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            vendor_code="VENDOR-1",
            legal_name="Vendor 1 Test Fixture",
        )
    )
    inp = CreatePODraftInput(
        vendor_id="VENDOR-1",
        process_id=str(uuid.uuid4()),
        amount=100.0,
        currency="LKR",
        tenant_id=str(BPMFLOW_DEMO_TENANT_ID),
    )
    out = await create_po_draft(session=None, input_data=inp)
    assert out.status == "DRAFT"


@pytest.mark.asyncio
async def test_email_dry_run_never_claims_provider_acceptance():
    agent2_settings.EMAIL_DRY_RUN = True
    result = await dispatch_email(
        recipient="a@example.com",
        subject="Test",
        body_plain="Body",
        body_html="<p>Body</p>",
    )
    assert result.status == "DRY_RUN"
    assert result.status != "ACCEPTED_BY_PROVIDER"


def test_production_rejects_email_dry_run(monkeypatch):
    monkeypatch.setattr(core_settings, "ENV", "production")
    monkeypatch.setattr(core_settings, "EMAIL_DRY_RUN", True)
    monkeypatch.setattr(core_settings, "GEMINI_API_KEY", "real-key")
    monkeypatch.setattr(core_settings, "GEMINI_OFFLINE", False)
    monkeypatch.setattr(core_settings, "MOCK_LLM", False)
    with pytest.raises(RuntimeError, match="EMAIL_DRY_RUN"):
        core_settings.assert_production_llm_config()


def test_trace_sanitizer_redacts_secrets():
    raw = {
        "decision_reason": "Send email api_key=secret123",
        "plan_reasoning": "Bearer abc.def.ghi",
        "execution_events": [{"tool": "send_email", "status": "SUCCESS", "error": ""}],
    }
    safe = sanitize_execution_explanation(raw)
    assert "secret123" not in safe["decision_reason"]
    assert "Bearer" not in safe["plan_summary"]


def test_side_effect_tools_registered():
    assert "send_email" in SIDE_EFFECT_TOOLS
    assert "create_po_draft" in SIDE_EFFECT_TOOLS


def test_idempotency_key_stable():
    key = generate_idempotency_key("p1", "t1", "send_email")
    assert key == "p1-t1-send_email"
