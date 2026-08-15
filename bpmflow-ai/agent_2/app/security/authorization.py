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
}

FORBIDDEN_ACTIONS: Set[str] = {
    ActionPermission.APPROVE_PURCHASE.value,
    ActionPermission.APPROVE_PAYMENT.value,
    ActionPermission.EXECUTE_PAYMENT.value,
    ActionPermission.CHANGE_OFFICIAL_WORKFLOW.value,
    ActionPermission.BYPASS_AGENT4.value,
    ActionPermission.MODIFY_SECURITY_POLICY.value,
}


def is_permitted(action: str) -> bool:
    """
    Check if an action string is permitted under Agent 2's hard-coded authorization matrix.

    :param action: Action or tool name string
    :return: True ONLY if action is explicitly allowed; False otherwise (default-deny).
    """
    if not action:
        return False
    action_clean = action.strip().lower()
    return action_clean in ALLOWED_ACTIONS
