"""
Agent 2 — Tool Input & Output Pydantic Schemas

Defines strongly-typed input parameters and return payloads for all 12 tools registered in ToolRegistry.
"""

from typing import Any, Dict, List
from pydantic import BaseModel, Field


# 1. create_workflow_task
class CreateTaskInput(BaseModel):
    process_id: str = Field(..., description="Target process instance UUID string")
    title: str = Field(..., description="Task title")
    task_type: str = Field(default="MANUAL", description="Task category: MANUAL, AUTOMATED, HUMAN_APPROVAL")
    assigned_role: str = Field(default="assigned_employee", description="Target role assignment")
    sla_hours: float = Field(default=24.0, ge=0.0, description="SLA duration target in hours")
    priority: str = Field(default="MEDIUM", description="Task priority")
    description: str = Field(default="", description="Detailed description")


class CreateTaskOutput(BaseModel):
    task_id: str = Field(..., description="Created task UUID string")
    status: str = Field(..., description="Task status")
    created_at: str = Field(..., description="ISO creation timestamp")


# 2. update_task
class UpdateTaskInput(BaseModel):
    task_id: str = Field(..., description="Target task UUID string")
    status: str = Field(..., description="New status (IN_PROGRESS, COMPLETED, FAILED, CANCELLED)")
    assigned_to: str = Field(default="", description="User email assigned to task")
    result_notes: str = Field(default="", description="Completion notes or result payload summary")


class UpdateTaskOutput(BaseModel):
    task_id: str = Field(..., description="Task UUID string")
    status: str = Field(..., description="Updated status")
    updated_at: str = Field(..., description="ISO update timestamp")


# 3. send_email
class SendEmailInput(BaseModel):
    recipient: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Email text or HTML body")
    process_id: str = Field(..., description="Associated process instance ID")
    task_id: str = Field(..., description="Associated task ID")
    recipient_role: str = Field(default="requester", description="Role of the recipient")
    template_name: str = Field(default="", description="Optional template name")


class SendEmailOutput(BaseModel):
    status: str = Field(..., description="Dispatch status (SENT, DRY_RUN, FAILED)")
    message_id: str = Field(..., description="Unique email message identifier")
    recipient: str = Field(..., description="Recipient email address")


# 4. send_reminder
class SendReminderInput(BaseModel):
    recipient: str = Field(..., description="Approver email address")
    task_id: str = Field(..., description="Delayed task ID")
    elapsed_hours: float = Field(..., ge=0.0, description="Hours elapsed")
    sla_hours: float = Field(..., ge=0.0, description="Target SLA hours")
    message: str = Field(default="", description="Optional custom reminder message")


class SendReminderOutput(BaseModel):
    status: str = Field(..., description="Reminder dispatch status")
    task_id: str = Field(..., description="Target task ID")
    notified_at: str = Field(..., description="ISO notification timestamp")


# 5. create_po_draft
class CreatePODraftInput(BaseModel):
    vendor_id: str = Field(..., description="Approved vendor ID")
    amount: float = Field(..., gt=0.0, description="PO amount")
    process_id: str = Field(..., description="Process instance ID")
    items_summary: str = Field(default="", description="Summary of requested items")


class CreatePODraftOutput(BaseModel):
    po_number: str = Field(..., description="Generated PO number string")
    status: str = Field(..., description="PO draft status")
    amount: float = Field(..., description="PO amount")
    created_at: str = Field(..., description="ISO creation timestamp")


# 6. request_quotation
class RequestQuotationInput(BaseModel):
    vendor_email: str = Field(..., description="Vendor contact email")
    items: str = Field(..., description="Item specifications and quantities")
    required_by: str = Field(default="", description="Required ISO date")


class RequestQuotationOutput(BaseModel):
    quotation_id: str = Field(..., description="Quotation request ID")
    status: str = Field(..., description="Quotation request status")
    requested_at: str = Field(..., description="ISO request timestamp")


# 7. update_procurement_record
class UpdateProcurementRecordInput(BaseModel):
    record_id: str = Field(..., description="ERP record ID")
    status: str = Field(..., description="New record status")
    notes: str = Field(default="", description="Audit notes")


class UpdateProcurementRecordOutput(BaseModel):
    record_id: str = Field(..., description="ERP record ID")
    status: str = Field(..., description="Updated record status")
    updated_at: str = Field(..., description="ISO update timestamp")


# 8. schedule_escalation
class ScheduleEscalationInput(BaseModel):
    task_id: str = Field(..., description="Target task ID")
    escalation_role: str = Field(..., description="Target escalation role")
    delay_minutes: float = Field(default=60.0, ge=0.0, description="Delay minutes before escalation")


class ScheduleEscalationOutput(BaseModel):
    job_id: str = Field(..., description="Scheduled job ID")
    status: str = Field(..., description="Job scheduling status")
    scheduled_for: str = Field(..., description="ISO execution timestamp")


# 9. create_exception
class CreateExceptionInput(BaseModel):
    process_id: str = Field(..., description="Target process instance ID")
    task_id: str = Field(..., description="Target task ID")
    severity: str = Field(..., description="Severity (LOW, MEDIUM, HIGH, CRITICAL)")
    reason: str = Field(..., description="Detailed exception description")


class CreateExceptionOutput(BaseModel):
    exception_id: str = Field(..., description="Created exception record ID")
    status: str = Field(..., description="Exception status")
    created_at: str = Field(..., description="ISO creation timestamp")


# 10. get_process_history
class GetProcessHistoryInput(BaseModel):
    process_id: str = Field(..., description="Target process instance UUID string")
    limit: int = Field(default=50, ge=1, le=500, description="Max event rows to fetch")


class GetProcessHistoryOutput(BaseModel):
    process_id: str = Field(..., description="Target process instance ID")
    events: List[Dict[str, Any]] = Field(default_factory=list, description="List of process workflow event dicts")
    count: int = Field(..., description="Event count returned")


# 11. get_task_history
class GetTaskHistoryInput(BaseModel):
    task_id: str = Field(..., description="Target task UUID string")


class GetTaskHistoryOutput(BaseModel):
    task_id: str = Field(..., description="Target task ID")
    attempts: List[Dict[str, Any]] = Field(default_factory=list, description="Execution attempt dicts")
    receipts: List[Dict[str, Any]] = Field(default_factory=list, description="Execution receipt dicts")


# 12. calculate_kpi
class CalculateKPIInput(BaseModel):
    process_type: str = Field(default="procurement", description="Process type category")
    days_back: int = Field(default=30, ge=1, description="Lookback window in days")


class CalculateKPIOutput(BaseModel):
    process_type: str = Field(..., description="Process type category")
    avg_cycle_time_hours: float = Field(..., description="Average process cycle duration in hours")
    completion_rate: float = Field(..., description="Process completion percentage")
    sla_compliance_rate: float = Field(..., description="SLA compliance percentage")
    throughput: int = Field(..., description="Total completed processes")
    bottleneck_task: str = Field(..., description="Bottleneck task identifier")
