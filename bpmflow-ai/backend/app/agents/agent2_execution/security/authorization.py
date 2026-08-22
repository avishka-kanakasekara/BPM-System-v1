"""
Agent 2 — Authorization & Hard-Coded Permission Matrix

Enforces Rule #4 Non-Negotiable invariant:
The permission matrix is hard-coded, not learned or inferred.
Agent 2 may create/update tasks, send email/reminders, create PO drafts, request quotations,
update mock ERP, analyze processes, and generate optimization proposals.
Agent 2 may NEVER approve a purchase, approve/execute a payment, change official workflow definitions,
bypass Agent 4, or modify security policy.

Default-deny policy: Any action not explicitly listed in ALLOWED_ACTIONS is strictly forbidden.
"""

from enum import Enum
from typing import Set


class ActionPermission(str, Enum):
    # Allowed actions
    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"
    SEND_EMAIL = "send_email"
    SEND_REMINDER = "send_reminder"
    SCHEDULE_REMINDER = "schedule_reminder"
    CREATE_PO_DRAFT = "create_po_draft"
    REQUEST_QUOTATION = "request_quotation"
    UPDATE_MOCK_ERP = "update_mock_erp"
    ANALYZE_PROCESS = "analyze_process"
    GENERATE_OPTIMIZATION_PROPOSAL = "generate_optimization_proposal"

    # Explicitly forbidden actions
    APPROVE_PURCHASE = "approve_purchase"
    APPROVE_PAYMENT = "approve_payment"
    EXECUTE_PAYMENT = "execute_payment"
    CHANGE_OFFICIAL_WORKFLOW = "change_official_workflow"
    BYPASS_AGENT4 = "bypass_agent4"
    MODIFY_SECURITY_POLICY = "modify_security_policy"


# Registered tool names are canonical aliases of the hard-coded permission matrix.
ACTION_ALIASES = {
    "create_workflow_task": ActionPermission.CREATE_TASK.value,
    "create_task": ActionPermission.CREATE_TASK.value,
    "update_task": ActionPermission.UPDATE_TASK.value,
    "send_email": ActionPermission.SEND_EMAIL.value,
    "send_reminder": ActionPermission.SEND_REMINDER.value,
    "schedule_reminder": ActionPermission.SCHEDULE_REMINDER.value,
    "schedule_escalation": ActionPermission.SCHEDULE_REMINDER.value,
    "create_po_draft": ActionPermission.CREATE_PO_DRAFT.value,
    "request_quotation": ActionPermission.REQUEST_QUOTATION.value,
    "update_procurement_record": ActionPermission.UPDATE_MOCK_ERP.value,
    "update_mock_erp": ActionPermission.UPDATE_MOCK_ERP.value,
    "create_exception": ActionPermission.CREATE_TASK.value,
    "get_process_history": ActionPermission.ANALYZE_PROCESS.value,
    "get_task_history": ActionPermission.ANALYZE_PROCESS.value,
    "calculate_kpi": ActionPermission.ANALYZE_PROCESS.value,
    "analyze_process": ActionPermission.ANALYZE_PROCESS.value,
    "generate_optimization_proposal": ActionPermission.GENERATE_OPTIMIZATION_PROPOSAL.value,
}

ALLOWED_ACTIONS: Set[str] = {
    ActionPermission.CREATE_TASK.value,
    ActionPermission.UPDATE_TASK.value,
    ActionPermission.SEND_EMAIL.value,
    ActionPermission.SEND_REMINDER.value,
    ActionPermission.SCHEDULE_REMINDER.value,
    ActionPermission.CREATE_PO_DRAFT.value,
    ActionPermission.REQUEST_QUOTATION.value,
    ActionPermission.UPDATE_MOCK_ERP.value,
    ActionPermission.ANALYZE_PROCESS.value,
    ActionPermission.GENERATE_OPTIMIZATION_PROPOSAL.value,
    *ACTION_ALIASES.keys(),
}

FORBIDDEN_ACTIONS: Set[str] = {
    ActionPermission.APPROVE_PURCHASE.value,
    ActionPermission.APPROVE_PAYMENT.value,
    ActionPermission.EXECUTE_PAYMENT.value,
    ActionPermission.CHANGE_OFFICIAL_WORKFLOW.value,
    ActionPermission.BYPASS_AGENT4.value,
    ActionPermission.MODIFY_SECURITY_POLICY.value,
}


def canonical_action(action: str) -> str:
    """Map a registered tool name onto the hard-coded permission matrix."""
    if not action:
        return ""
    action_clean = action.strip().lower()
    return ACTION_ALIASES.get(action_clean, action_clean)


def is_permitted(action: str) -> bool:
    """
    Check if an action string is permitted under Agent 2's hard-coded authorization matrix.

    :param action: Action or tool name string
    :return: True ONLY if action is explicitly allowed; False otherwise (default-deny).
    """
    if not action:
        return False
    action_clean = action.strip().lower()
    if action_clean in FORBIDDEN_ACTIONS:
        return False
    return canonical_action(action_clean) in ALLOWED_ACTIONS or action_clean in ALLOWED_ACTIONS
