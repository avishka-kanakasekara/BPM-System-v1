"""Explicit BPMFlow Demo Company tool registrations. Never auto-runs."""

from __future__ import annotations

from uuid import UUID

from app.agents.agent2_execution.tools import registry as agent2_registry
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
    MatchInvoiceInput,
    MatchInvoiceOutput,
    RequestQuotationInput,
    RequestQuotationOutput,
    ScheduleEscalationInput,
    ScheduleEscalationOutput,
    SendEmailOutput,
    SendReminderInput,
    SendReminderOutput,
    UpdateProcurementRecordInput,
    UpdateProcurementRecordOutput,
    UpdateTaskInput,
    UpdateTaskOutput,
)
from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID

from .constants import ToolActionCode, ToolCategory
from .implementations import REGISTERED_IMPLEMENTATIONS
from .schemas import RegisterToolInput, ToolRegistryRecord
from .service import ToolRegistryService


def _schema(model) -> dict:
    schema = model.model_json_schema()
    return {
        "type": schema.get("type") or "object",
        "properties": schema.get("properties") or {},
        "required": schema.get("required") or [],
    }


def bpmflow_demo_tool_specs() -> list[RegisterToolInput]:
    """Catalog of real Agent 2 tools. No invented handlers."""
    return [
        RegisterToolInput(
            tool_name="create_workflow_task",
            display_name="Create workflow task",
            description="Create a new workflow task",
            tool_category=ToolCategory.TASK,
            action_code=ToolActionCode.CREATE_TASK,
            implementation_key="task.create_workflow_task",
            requires_authorization=True,
            allowed_step_types=["HUMAN_TASK", "SYSTEM_ACTION"],
            required_permissions=["create_task"],
            input_schema=_schema(CreateTaskInput),
            output_schema=_schema(CreateTaskOutput),
        ),
        RegisterToolInput(
            tool_name="update_task",
            display_name="Update task",
            description="Update status or assignments of a workflow task",
            tool_category=ToolCategory.TASK,
            action_code=ToolActionCode.UPDATE_TASK,
            implementation_key="task.update_task",
            requires_authorization=True,
            allowed_step_types=["HUMAN_TASK", "SYSTEM_ACTION"],
            required_permissions=["update_task"],
            input_schema=_schema(UpdateTaskInput),
            output_schema=_schema(UpdateTaskOutput),
        ),
        RegisterToolInput(
            tool_name="send_email",
            display_name="Send email",
            description="Send an outbound communication. Recipients are employee IDs at execution time.",
            tool_category=ToolCategory.COMMUNICATION,
            action_code=ToolActionCode.SEND_EMAIL,
            implementation_key="communication.send_email",
            requires_authorization=True,
            allowed_step_types=["COMMUNICATION"],
            required_permissions=["send_email"],
            input_schema={
                "type": "object",
                "properties": {
                    "process_id": {"type": "string"},
                    "recipient_employee_ids": {"type": "array", "items": {"type": "string"}},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["process_id", "recipient_employee_ids", "subject", "body"],
            },
            output_schema=_schema(SendEmailOutput),
        ),
        RegisterToolInput(
            tool_name="send_reminder",
            display_name="Send reminder",
            description="Send an SLA reminder. Recipients are employee IDs at execution time.",
            tool_category=ToolCategory.NOTIFICATION,
            action_code=ToolActionCode.SEND_REMINDER,
            implementation_key="communication.send_reminder",
            requires_authorization=True,
            allowed_step_types=["COMMUNICATION", "HUMAN_TASK"],
            required_permissions=["send_reminder"],
            input_schema=_schema(SendReminderInput),
            output_schema=_schema(SendReminderOutput),
        ),
        RegisterToolInput(
            tool_name="create_purchase_order",
            display_name="Create purchase order",
            description="Generate a purchase order draft via the existing Agent 2 procurement tool",
            tool_category=ToolCategory.PROCUREMENT,
            action_code=ToolActionCode.CREATE_PURCHASE_ORDER,
            implementation_key="procurement.create_purchase_order",
            requires_authorization=True,
            allowed_step_types=["SYSTEM_ACTION"],
            required_permissions=["create_po_draft"],
            input_schema=_schema(CreatePODraftInput),
            output_schema=_schema(CreatePODraftOutput),
        ),
        RegisterToolInput(
            tool_name="request_quotation",
            display_name="Request quotation",
            description="Request a vendor quotation",
            tool_category=ToolCategory.PROCUREMENT,
            action_code=ToolActionCode.REQUEST_QUOTATION,
            implementation_key="procurement.request_quotation",
            requires_authorization=True,
            allowed_step_types=["SYSTEM_ACTION", "COMMUNICATION"],
            required_permissions=["request_quotation"],
            input_schema=_schema(RequestQuotationInput),
            output_schema=_schema(RequestQuotationOutput),
        ),
        RegisterToolInput(
            tool_name="update_procurement_record",
            display_name="Update procurement record",
            description="Update a procurement record on process metadata",
            tool_category=ToolCategory.PROCUREMENT,
            action_code=ToolActionCode.UPDATE_PROCUREMENT_RECORD,
            implementation_key="procurement.update_procurement_record",
            requires_authorization=True,
            allowed_step_types=["SYSTEM_ACTION"],
            required_permissions=["update_mock_erp"],
            input_schema=_schema(UpdateProcurementRecordInput),
            output_schema=_schema(UpdateProcurementRecordOutput),
        ),
        RegisterToolInput(
            tool_name="schedule_escalation",
            display_name="Schedule escalation",
            description="Schedule a delayed task escalation job",
            tool_category=ToolCategory.NOTIFICATION,
            action_code=ToolActionCode.ESCALATE,
            implementation_key="scheduler.schedule_escalation",
            requires_authorization=True,
            allowed_step_types=["EXCEPTION_HANDLING", "SYSTEM_ACTION"],
            required_permissions=["schedule_reminder"],
            input_schema=_schema(ScheduleEscalationInput),
            output_schema=_schema(ScheduleEscalationOutput),
        ),
        RegisterToolInput(
            tool_name="create_exception",
            display_name="Create exception",
            description="Raise an execution exception ticket",
            tool_category=ToolCategory.SYSTEM,
            action_code=ToolActionCode.CREATE_EXCEPTION,
            implementation_key="exception.create_exception",
            requires_authorization=True,
            allowed_step_types=["EXCEPTION_HANDLING", "SYSTEM_ACTION"],
            required_permissions=["create_task"],
            input_schema=_schema(CreateExceptionInput),
            output_schema=_schema(CreateExceptionOutput),
        ),
        RegisterToolInput(
            tool_name="get_process_history",
            display_name="Get process history",
            description="Retrieve workflow event history",
            tool_category=ToolCategory.DOCUMENT,
            action_code=ToolActionCode.GET_PROCESS_HISTORY,
            implementation_key="analytics.get_process_history",
            requires_authorization=False,
            allowed_step_types=["DOCUMENT_REVIEW", "VALIDATION", "SYSTEM_ACTION"],
            required_permissions=["analyze_process"],
            input_schema=_schema(GetProcessHistoryInput),
            output_schema=_schema(GetProcessHistoryOutput),
        ),
        RegisterToolInput(
            tool_name="get_task_history",
            display_name="Get task history",
            description="Retrieve task attempts and execution receipts",
            tool_category=ToolCategory.DOCUMENT,
            action_code=ToolActionCode.GET_TASK_HISTORY,
            implementation_key="analytics.get_task_history",
            requires_authorization=False,
            allowed_step_types=["DOCUMENT_REVIEW", "VALIDATION", "SYSTEM_ACTION"],
            required_permissions=["analyze_process"],
            input_schema=_schema(GetTaskHistoryInput),
            output_schema=_schema(GetTaskHistoryOutput),
        ),
        RegisterToolInput(
            tool_name="calculate_kpi",
            display_name="Calculate KPI",
            description="Calculate aggregated KPI metrics",
            tool_category=ToolCategory.SYSTEM,
            action_code=ToolActionCode.CALCULATE_KPI,
            implementation_key="analytics.calculate_kpi",
            requires_authorization=False,
            allowed_step_types=["SYSTEM_ACTION", "VALIDATION"],
            required_permissions=["analyze_process"],
            input_schema=_schema(CalculateKPIInput),
            output_schema=_schema(CalculateKPIOutput),
        ),
        RegisterToolInput(
            tool_name="match_invoice",
            display_name="Match invoice",
            description="Deterministically match a persisted invoice to a persisted purchase order",
            tool_category=ToolCategory.VALIDATION,
            action_code=ToolActionCode.MATCH_INVOICE,
            implementation_key="procurement.match_invoice",
            requires_authorization=True,
            allowed_step_types=["VALIDATION", "SYSTEM_ACTION"],
            required_permissions=["match_invoice"],
            input_schema=_schema(MatchInvoiceInput),
            output_schema=_schema(MatchInvoiceOutput),
        ),
    ]


async def seed_bpmflow_tool_registry(
    service: ToolRegistryService,
    *,
    tenant_id: UUID = BPMFLOW_DEMO_TENANT_ID,
) -> list[ToolRegistryRecord]:
    """Register real Agent 2 tools for a tenant. Call explicitly."""
    created: list[ToolRegistryRecord] = []
    for spec in bpmflow_demo_tool_specs():
        agent2_name = REGISTERED_IMPLEMENTATIONS[spec.implementation_key]
        if not agent2_registry.contains(agent2_name):
            raise RuntimeError(
                f"Cannot seed {spec.tool_name}: Agent 2 tool {agent2_name!r} is not registered"
            )
        created.append(await service.register_tool(spec, tenant_id=tenant_id))
    return created
