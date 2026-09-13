"""Safe implementation allow-list. DB never supplies import paths."""

from __future__ import annotations

from dataclasses import dataclass

# Maps a stable implementation_key to the existing in-process Agent 2 tool name.
# Agent 2 ToolRegistry remains the execution layer until a later phase.
REGISTERED_IMPLEMENTATIONS: dict[str, str] = {
    "task.create_workflow_task": "create_workflow_task",
    "task.update_task": "update_task",
    "communication.send_email": "send_email",
    "communication.send_reminder": "send_reminder",
    "procurement.create_purchase_order": "create_po_draft",
    "procurement.match_invoice": "match_invoice",
    "procurement.request_quotation": "request_quotation",
    "procurement.update_procurement_record": "update_procurement_record",
    "scheduler.schedule_escalation": "schedule_escalation",
    "exception.create_exception": "create_exception",
    "analytics.get_process_history": "get_process_history",
    "analytics.get_task_history": "get_task_history",
    "analytics.calculate_kpi": "calculate_kpi",
}

ALLOWED_IMPLEMENTATION_KEYS = frozenset(REGISTERED_IMPLEMENTATIONS)


@dataclass(frozen=True)
class ImplementationBinding:
    implementation_key: str
    agent2_tool_name: str


def resolve_implementation(implementation_key: str) -> ImplementationBinding:
    """Return the allow-listed Agent 2 tool name. Never imports arbitrary modules."""
    key = (implementation_key or "").strip()
    agent2_name = REGISTERED_IMPLEMENTATIONS.get(key)
    if agent2_name is None:
        raise KeyError(key)
    return ImplementationBinding(implementation_key=key, agent2_tool_name=agent2_name)


def is_registered_implementation(implementation_key: str) -> bool:
    return (implementation_key or "").strip() in REGISTERED_IMPLEMENTATIONS
