"""
G4 exit tests — authorized dispatch produces PO draft + SUCCESS receipt.
"""

from __future__ import annotations

import uuid

import pytest

from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID
from app.procurement.schemas import CreateVendorInput
from app.procurement.service import get_procurement
from app.agents.agent2_execution.agent.agent import Agent2
from app.agents.agent2_execution.agent.cognitive_pipeline import node_catalog
from app.agents.agent2_execution.agent.planner_fallback import (
    PlanValidationError,
    validate_execution_plan,
)
from app.agents.agent2_execution.database.persistence import (
    clear_memory_process_metadata,
    get_memory_process_metadata,
)
from app.agents.agent2_execution.execution.execution_engine import execute_with_recovery
from app.agents.agent2_execution.execution.idempotency import clear_memory_receipts
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.llm.schemas import AgentMessage, ExecutionPlan
from app.agents.agent2_execution.security.tool_guard import ExecutionGuardContext, ToolGuard


@pytest.fixture(autouse=True)
def _reset_memory_stores():
    clear_memory_receipts()
    clear_memory_process_metadata()
    yield
    clear_memory_receipts()
    clear_memory_process_metadata()


@pytest.mark.asyncio
async def test_g4_authorized_po_draft_dispatch_success_receipt_and_metadata():
    """Single AUTHORIZED dispatch creates PO draft evidence and SUCCESS receipt."""
    get_procurement().create_vendor(
        CreateVendorInput(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            vendor_code="VENDOR-ACME",
            legal_name="Acme Test Fixture Vendor",
            notes="Explicit G4 test fixture. Not a production fallback.",
        )
    )
    proc_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    message = AgentMessage(
        message_id=f"msg-{uuid.uuid4().hex[:8]}",
        process_id=proc_id,
        trace_id="trace-g4-po",
        sender="agent_4",
        receiver="agent_2",
        task_type="EXECUTE_TASK",
        payload={
            "task_id": task_id,
            "task_title": "Create purchase order draft",
            "process_type": "procurement",
            "parameters": {
                "tool_name": "create_po_draft",
                "vendor_id": "VENDOR-ACME",
                "amount": 4565.0,
                "currency": "USD",
                "process_id": proc_id,
                "task_id": task_id,
                "tenant_id": str(BPMFLOW_DEMO_TENANT_ID),
            },
        },
        confidence=1.0,
        status="AUTHORIZED",
    )

    agent = Agent2(gemini_client=GeminiClient(is_offline=True))
    response = await agent.handle(message, session=None)

    assert response.status == "EXECUTION_RESULT"
    assert response.payload["receipt_status"] == "SUCCESS"
    assert response.payload["tool_name"] == "create_po_draft"
    assert "create_po_draft" in response.payload.get("tools_executed", [])

    record = get_procurement().get_purchase_order_for_process(
        tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=uuid.UUID(proc_id)
    )
    assert record is not None
    assert record.status == "DRAFT"
    assert str(record.po_number).startswith("PO-")
    meta = get_memory_process_metadata(proc_id)
    purchase_order = meta.get("purchase_order_ref") or meta.get("purchase_order") or {}
    assert purchase_order.get("status") == "DRAFT"
    assert purchase_order.get("vendor_id") == "VENDOR-ACME"
    assert float(purchase_order.get("total") or purchase_order.get("amount") or 0) > 0
    assert purchase_order.get("po_number", "").startswith("PO-")


@pytest.mark.asyncio
async def test_g4_idempotency_replay_returns_same_success_receipt():
    get_procurement().create_vendor(
        CreateVendorInput(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            vendor_code="VENDOR-ACME",
            legal_name="Acme Test Fixture Vendor",
            notes="Explicit G4 test fixture. Not a production fallback.",
        )
    )
    proc_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    params = {
        "vendor_id": "VENDOR-ACME",
        "amount": 1200.0,
        "currency": "USD",
        "process_id": proc_id,
        "task_id": task_id,
        "tenant_id": str(BPMFLOW_DEMO_TENANT_ID),
    }
    guard = ExecutionGuardContext(
        message_status="AUTHORIZED",
        process_stage="WORKFLOW_EXECUTION",
        process_id=proc_id,
    )
    client = GeminiClient(is_offline=True)

    first = await execute_with_recovery(
        process_id=proc_id,
        task_id=task_id,
        tool_name="create_po_draft",
        parameters=params,
        session=None,
        gemini_client=client,
        guard_context=guard,
    )
    second = await execute_with_recovery(
        process_id=proc_id,
        task_id=task_id,
        tool_name="create_po_draft",
        parameters=params,
        session=None,
        gemini_client=client,
        guard_context=guard,
    )

    assert first.status == "SUCCESS"
    assert second.status == "SUCCESS"
    assert second.id == first.id
    assert second.idempotency_key == first.idempotency_key


@pytest.mark.asyncio
async def test_g4_tool_guard_blocks_non_authorized_message_status():
    guard = ToolGuard(session=None)
    result = await guard.check(
        "create_po_draft",
        {"vendor_id": "V1", "amount": 100, "process_id": str(uuid.uuid4())},
        guard_context=ExecutionGuardContext(
            message_status="PENDING",
            process_stage="WORKFLOW_EXECUTION",
        ),
    )
    assert result.allowed is False
    assert result.error == "NOT_AUTHORIZED"


@pytest.mark.asyncio
async def test_g4_tool_guard_blocks_mutating_tool_wrong_stage():
    guard = ToolGuard(session=None)
    result = await guard.check(
        "create_po_draft",
        {"vendor_id": "V1", "amount": 100, "process_id": str(uuid.uuid4())},
        guard_context=ExecutionGuardContext(
            message_status="AUTHORIZED",
            process_stage="DRAFT",
        ),
    )
    assert result.allowed is False
    assert result.error == "STAGE_NOT_AUTHORIZED"


def test_g4_empty_plan_validation_fails_explicitly():
    with pytest.raises(PlanValidationError):
        validate_execution_plan(
            ExecutionPlan(
                task_id="t1",
                objective="",
                steps=[],
                selected_tools=[],
                reasoning_summary="empty",
                risk_level="LOW",
                confidence=0.5,
            )
        )


def test_g4_cognitive_pipeline_has_eleven_nodes():
    nodes = node_catalog()
    assert len(nodes) == 11
    names = {n["name"] for n in nodes}
    assert "PERCEIVE" in names
    assert "PLAN" in names
    assert "ACT" in names
    assert "RECORD" in names
