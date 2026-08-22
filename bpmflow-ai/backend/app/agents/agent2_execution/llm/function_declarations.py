"""
Agent 2 — Gemini Function Declarations (12 Tools)

Declares Gemini function-calling schemas for all 12 tools Agent 2 is equipped to use.
These declarations are passed to Gemini during function-calling calls.

Non-Negotiable Rule #1: Gemini only proposes a function call structure. It NEVER executes.
Non-Negotiable Rule #2: Every proposed call must be validated through Tool Guard.
Non-Negotiable Rule #4: Only actions in the ALLOWED matrix are present here.
"""

from typing import Any, Dict, List

ALL_TOOL_DECLARATIONS: List[Dict[str, Any]] = [
    {
        "name": "create_workflow_task",
        "description": "Create a new sub-task within a process instance.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "process_id": {"type": "STRING", "description": "Target process instance ID"},
                "title": {"type": "STRING", "description": "Title of the new task"},
                "task_type": {"type": "STRING", "description": "Task type (MANUAL, AUTOMATED, HUMAN_APPROVAL)"},
                "assigned_role": {"type": "STRING", "description": "Role assigned to complete task"},
                "sla_hours": {"type": "NUMBER", "description": "SLA target duration in hours"},
                "priority": {"type": "STRING", "description": "Priority (LOW, MEDIUM, HIGH, URGENT)"},
            },
            "required": ["process_id", "title", "task_type", "assigned_role"],
        },
    },
    {
        "name": "update_task",
        "description": "Update the status, assignment, or results of an existing task.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task_id": {"type": "STRING", "description": "Target task ID"},
                "status": {"type": "STRING", "description": "New status (IN_PROGRESS, COMPLETED, FAILED, CANCELLED)"},
                "assigned_to": {"type": "STRING", "description": "User email assigned to task"},
                "result_notes": {"type": "STRING", "description": "Completion notes or result summary"},
            },
            "required": ["task_id", "status"],
        },
    },
    {
        "name": "send_email",
        "description": "Send a notification email to an authorized role recipient (Rule #6).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "recipient": {"type": "STRING", "description": "Recipient email address"},
                "subject": {"type": "STRING", "description": "Email subject line"},
                "body": {"type": "STRING", "description": "Email body content"},
                "process_id": {"type": "STRING", "description": "Associated process instance ID"},
                "task_id": {"type": "STRING", "description": "Associated task ID"},
                "recipient_role": {"type": "STRING", "description": "Role of recipient (requester, manager, finance_officer, etc.)"},
            },
            "required": ["recipient", "subject", "body", "process_id", "task_id"],
        },
    },
    {
        "name": "send_reminder",
        "description": "Send an SLA warning or reminder email to an assigned approver.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "recipient": {"type": "STRING", "description": "Approver email address"},
                "task_id": {"type": "STRING", "description": "Task ID experiencing delay"},
                "elapsed_hours": {"type": "NUMBER", "description": "Hours elapsed since assignment"},
                "sla_hours": {"type": "NUMBER", "description": "Target SLA hours"},
            },
            "required": ["recipient", "task_id", "elapsed_hours", "sla_hours"],
        },
    },
    {
        "name": "create_po_draft",
        "description": "Generate a purchase order draft in the mock ERP system.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "vendor_id": {"type": "STRING", "description": "Approved vendor ID"},
                "amount": {"type": "NUMBER", "description": "Total purchase order amount"},
                "items_summary": {"type": "STRING", "description": "Summary of items requested"},
                "process_id": {"type": "STRING", "description": "Target process instance ID"},
            },
            "required": ["vendor_id", "amount", "process_id"],
        },
    },
    {
        "name": "request_quotation",
        "description": "Request a vendor quotation for procurement items.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "vendor_email": {"type": "STRING", "description": "Vendor contact email"},
                "items": {"type": "STRING", "description": "Item specifications and quantities"},
                "required_by": {"type": "STRING", "description": "ISO date quotation is needed by"},
            },
            "required": ["vendor_email", "items"],
        },
    },
    {
        "name": "update_procurement_record",
        "description": "Update mock ERP procurement record metadata.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "record_id": {"type": "STRING", "description": "ERP procurement record ID"},
                "status": {"type": "STRING", "description": "New ERP record status"},
                "notes": {"type": "STRING", "description": "Audit notes"},
            },
            "required": ["record_id", "status"],
        },
    },
    {
        "name": "schedule_escalation",
        "description": "Schedule a timed escalation event if SLA threshold is exceeded.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task_id": {"type": "STRING", "description": "Target task ID"},
                "escalation_role": {"type": "STRING", "description": "Target escalation contact role"},
                "delay_minutes": {"type": "NUMBER", "description": "Delay before triggering escalation"},
            },
            "required": ["task_id", "escalation_role", "delay_minutes"],
        },
    },
    {
        "name": "create_exception",
        "description": "Raise an execution exception ticket for human supervisor intervention.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "process_id": {"type": "STRING", "description": "Target process instance ID"},
                "task_id": {"type": "STRING", "description": "Target task ID"},
                "severity": {"type": "STRING", "description": "Severity (LOW, MEDIUM, HIGH, CRITICAL)"},
                "reason": {"type": "STRING", "description": "Detailed exception description"},
            },
            "required": ["process_id", "task_id", "severity", "reason"],
        },
    },
    {
        "name": "get_process_history",
        "description": "Retrieve execution event history for a process instance.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "process_id": {"type": "STRING", "description": "Target process instance ID"},
                "limit": {"type": "NUMBER", "description": "Maximum event rows to fetch"},
            },
            "required": ["process_id"],
        },
    },
    {
        "name": "get_task_history",
        "description": "Retrieve task execution attempt logs and tool call receipts.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task_id": {"type": "STRING", "description": "Target task ID"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "calculate_kpi",
        "description": "Calculate aggregated KPI metrics for a process category.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "process_type": {"type": "STRING", "description": "Process type (e.g. procurement)"},
                "days_back": {"type": "NUMBER", "description": "Time window lookback in days"},
            },
            "required": ["process_type"],
        },
    },
]


def get_tool_declaration_by_name(name: str) -> Dict[str, Any]:
    """Retrieve a specific tool declaration dictionary by tool name."""
    name_clean = name.strip().lower()
    for tool in ALL_TOOL_DECLARATIONS:
        if tool["name"].lower() == name_clean:
            return tool
    return {}
