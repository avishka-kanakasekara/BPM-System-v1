"""
Agent 2 — Tool Implementation Unit Tests

Tests all 12 tools registered in ToolRegistry:
- Direct tool handler execution with valid input models
- Schema verification of returned output models
- Validation error handling for invalid parameter inputs
"""

import uuid
import pytest
from pydantic import ValidationError

from app.agents.agent2_execution.tools import registry
from app.agents.agent2_execution.tools.history_tools import get_process_history, get_task_history
from app.agents.agent2_execution.tools.kpi_tools import calculate_kpi
from app.agents.agent2_execution.tools.notification_tools import create_exception, send_email, send_reminder
from app.agents.agent2_execution.tools.procurement_tools import (
    create_po_draft,
    request_quotation,
    update_procurement_record,
)
from app.agents.agent2_execution.tools.scheduler_tools import schedule_escalation
from app.agents.agent2_execution.tools.schemas import (
    CalculateKPIInput,
    CalculateKPIOutput,
    CreateExceptionInput,
    CreateExceptionOutput,
    CreatePODraftInput,
    CreatePODraftOutput,
    CreateTaskInput,
    CreateTaskOutput,
    GetProcessHistoryInput,
    GetProcessHistoryOutput,
    GetTaskHistoryInput,
    GetTaskHistoryOutput,
    RequestQuotationInput,
    RequestQuotationOutput,
    ScheduleEscalationInput,
    ScheduleEscalationOutput,
    SendEmailInput,
    SendEmailOutput,
    SendReminderInput,
    SendReminderOutput,
    UpdateProcurementRecordInput,
    UpdateProcurementRecordOutput,
    UpdateTaskInput,
    UpdateTaskOutput,
)
from app.agents.agent2_execution.tools.task_tools import create_workflow_task, update_task


def test_registry_contains_all_12_tools():
    assert len(registry.list_tools()) == 12
    expected = {
        "create_workflow_task",
        "update_task",
        "send_email",
        "send_reminder",
        "create_po_draft",
        "request_quotation",
        "update_procurement_record",
        "schedule_escalation",
        "create_exception",
        "get_process_history",
        "get_task_history",
        "calculate_kpi",
    }
    registered = {t.name for t in registry.list_tools()}
    assert registered == expected


@pytest.mark.asyncio
async def test_create_workflow_task_tool():
    inp = CreateTaskInput(
        process_id=str(uuid.uuid4()),
        title="Validate Request",
        task_type="AUTOMATED",
        assigned_role="system",
        sla_hours=1.0,
    )
    out = await create_workflow_task(session=None, input_data=inp)
    assert isinstance(out, CreateTaskOutput)
    assert out.status == "PENDING"
    assert out.task_id != ""


@pytest.mark.asyncio
async def test_update_task_tool():
    inp = UpdateTaskInput(
        task_id=str(uuid.uuid4()),
        status="COMPLETED",
        assigned_to="david.brown@acmeglobal.com",
        result_notes="Validation passed",
    )
    out = await update_task(session=None, input_data=inp)
    assert isinstance(out, UpdateTaskOutput)
    assert out.status == "COMPLETED"


@pytest.mark.asyncio
async def test_send_email_tool():
    inp = SendEmailInput(
        recipient="alice.johnson@acmeglobal.com",
        subject="Request Received",
        body="Body text",
        process_id=str(uuid.uuid4()),
        task_id=str(uuid.uuid4()),
    )
    out = await send_email(session=None, input_data=inp)
    assert isinstance(out, SendEmailOutput)
    assert out.status in ["SENT", "DRY_RUN"]
    assert out.recipient == "alice.johnson@acmeglobal.com"


@pytest.mark.asyncio
async def test_send_reminder_tool():
    inp = SendReminderInput(
        recipient="frank.miller@acmeglobal.com",
        task_id=str(uuid.uuid4()),
        elapsed_hours=18.5,
        sla_hours=24.0,
    )
    out = await send_reminder(session=None, input_data=inp)
    assert isinstance(out, SendReminderOutput)
    assert out.status in ["SENT", "DRY_RUN"]


@pytest.mark.asyncio
async def test_create_po_draft_tool():
    inp = CreatePODraftInput(
        vendor_id="vendor-99",
        amount=4500.00,
        process_id=str(uuid.uuid4()),
        items_summary="5 Developer Laptops",
    )
    out = await create_po_draft(session=None, input_data=inp)
    assert isinstance(out, CreatePODraftOutput)
    assert out.status == "DRAFT"
    assert out.po_number.startswith("PO-")


@pytest.mark.asyncio
async def test_request_quotation_tool():
    inp = RequestQuotationInput(
        vendor_email="sales@vendor.com",
        items="10 Monitors",
        required_by="2026-08-30",
    )
    out = await request_quotation(session=None, input_data=inp)
    assert isinstance(out, RequestQuotationOutput)
    assert out.status == "REQUESTED"


@pytest.mark.asyncio
async def test_update_procurement_record_tool():
    inp = UpdateProcurementRecordInput(
        record_id="rec-erp-100",
        status="APPROVED",
        notes="Manager approved",
    )
    out = await update_procurement_record(session=None, input_data=inp)
    assert isinstance(out, UpdateProcurementRecordOutput)
    assert out.status == "APPROVED"


@pytest.mark.asyncio
async def test_schedule_escalation_tool():
    inp = ScheduleEscalationInput(
        task_id=str(uuid.uuid4()),
        escalation_role="escalation_contact",
        delay_minutes=30.0,
    )
    out = await schedule_escalation(session=None, input_data=inp)
    assert isinstance(out, ScheduleEscalationOutput)
    assert out.status == "SCHEDULED"


@pytest.mark.asyncio
async def test_create_exception_tool():
    inp = CreateExceptionInput(
        process_id=str(uuid.uuid4()),
        task_id=str(uuid.uuid4()),
        severity="HIGH",
        reason="Vendor quotation deadline exceeded",
    )
    out = await create_exception(session=None, input_data=inp)
    assert isinstance(out, CreateExceptionOutput)
    assert out.status == "OPEN"


@pytest.mark.asyncio
async def test_get_process_history_tool():
    inp = GetProcessHistoryInput(
        process_id=str(uuid.uuid4()),
        limit=10,
    )
    out = await get_process_history(session=None, input_data=inp)
    assert isinstance(out, GetProcessHistoryOutput)
    assert out.count >= 0


@pytest.mark.asyncio
async def test_get_task_history_tool():
    inp = GetTaskHistoryInput(
        task_id=str(uuid.uuid4()),
    )
    out = await get_task_history(session=None, input_data=inp)
    assert isinstance(out, GetTaskHistoryOutput)
    assert isinstance(out.attempts, list)


@pytest.mark.asyncio
async def test_calculate_kpi_tool():
    inp = CalculateKPIInput(
        process_type="procurement",
        days_back=30,
    )
    out = await calculate_kpi(session=None, input_data=inp)
    assert isinstance(out, CalculateKPIOutput)
    assert out.process_type == "procurement"
    assert out.avg_cycle_time_hours > 0.0


def test_tool_invalid_input_raises_validation_error():
    # Negative amount or missing vendor_id
    with pytest.raises(ValidationError):
        CreatePODraftInput(
            vendor_id="v-1",
            amount=-500.00,  # invalid (amount must be > 0)
            process_id="p-1",
        )

    with pytest.raises(ValidationError):
        CreateTaskInput(
            process_id="p-1",
            title="Title",
            sla_hours=-10.0,  # invalid (sla_hours must be >= 0)
        )
