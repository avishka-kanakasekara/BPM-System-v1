"""
Agent 2 — Tool System Initialization & Registration

Registers all 12 tools in the central ToolRegistry.
"""

from app.tools.history_tools import get_process_history, get_task_history
from app.tools.kpi_tools import calculate_kpi
from app.tools.notification_tools import create_exception, send_email, send_reminder
from app.tools.procurement_tools import (
    create_po_draft,
    request_quotation,
    update_procurement_record,
)
from app.tools.registry import registry
from app.tools.scheduler_tools import schedule_escalation
from app.tools.schemas import (
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
from app.tools.task_tools import create_workflow_task, update_task


def _register_all_tools():
    # 1. create_workflow_task
    registry.register(
        name="create_workflow_task",
        description="Create a new workflow task",
        input_schema=CreateTaskInput,
        output_schema=CreateTaskOutput,
        handler=create_workflow_task,
    )

    # 2. update_task
    registry.register(
        name="update_task",
        description="Update status or assignments of a workflow task",
        input_schema=UpdateTaskInput,
        output_schema=UpdateTaskOutput,
        handler=update_task,
    )

    # 3. send_email
    registry.register(
        name="send_email",
        description="Send an outbound role email",
        input_schema=SendEmailInput,
        output_schema=SendEmailOutput,
        handler=send_email,
    )

    # 4. send_reminder
    registry.register(
        name="send_reminder",
        description="Send an SLA reminder notification",
        input_schema=SendReminderInput,
        output_schema=SendReminderOutput,
        handler=send_reminder,
    )

    # 5. create_po_draft
    registry.register(
        name="create_po_draft",
        description="Generate purchase order draft in mock ERP",
        input_schema=CreatePODraftInput,
        output_schema=CreatePODraftOutput,
        handler=create_po_draft,
    )

    # 6. request_quotation
    registry.register(
        name="request_quotation",
        description="Request vendor quotation",
        input_schema=RequestQuotationInput,
        output_schema=RequestQuotationOutput,
        handler=request_quotation,
    )

    # 7. update_procurement_record
    registry.register(
        name="update_procurement_record",
        description="Update procurement record in mock ERP",
        input_schema=UpdateProcurementRecordInput,
        output_schema=UpdateProcurementRecordOutput,
        handler=update_procurement_record,
    )

    # 8. schedule_escalation
    registry.register(
        name="schedule_escalation",
        description="Schedule delayed task escalation job",
        input_schema=ScheduleEscalationInput,
        output_schema=ScheduleEscalationOutput,
        handler=schedule_escalation,
    )

    # 9. create_exception
    registry.register(
        name="create_exception",
        description="Raise an execution exception ticket",
        input_schema=CreateExceptionInput,
        output_schema=CreateExceptionOutput,
        handler=create_exception,
    )

    # 10. get_process_history
    registry.register(
        name="get_process_history",
        description="Retrieve workflow event history for a process instance",
        input_schema=GetProcessHistoryInput,
        output_schema=GetProcessHistoryOutput,
        handler=get_process_history,
    )

    # 11. get_task_history
    registry.register(
        name="get_task_history",
        description="Retrieve task attempts and execution receipts",
        input_schema=GetTaskHistoryInput,
        output_schema=GetTaskHistoryOutput,
        handler=get_task_history,
    )

    # 12. calculate_kpi
    registry.register(
        name="calculate_kpi",
        description="Calculate aggregated KPI metrics for a process category",
        input_schema=CalculateKPIInput,
        output_schema=CalculateKPIOutput,
        handler=calculate_kpi,
    )


# Automatically initialize tool registrations on package import
_register_all_tools()

__all__ = [
    "registry",
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
]
