"""
Agent 2 — Tool capability metadata for dashboard and frontend tools page.
"""

from typing import Any

from app.agents.agent2_execution.security import authorization
from app.agents.agent2_execution.tools.registry import registry

READ_ONLY_TOOLS = frozenset(
    {"get_process_history", "get_task_history", "calculate_kpi"}
)

TOOL_CATEGORIES: dict[str, str] = {
    "create_workflow_task": "Task Management",
    "update_task": "Task Management",
    "send_email": "Communication",
    "send_reminder": "Communication",
    "create_po_draft": "Procurement",
    "request_quotation": "Procurement",
    "update_procurement_record": "Procurement",
    "schedule_escalation": "Scheduling",
    "create_exception": "Exception Management",
    "get_process_history": "Analytics",
    "get_task_history": "Analytics",
    "calculate_kpi": "Analytics",
}

APPROVAL_REQUIRED: dict[str, bool] = {
    "create_workflow_task": True,
    "update_task": True,
    "send_email": True,
    "send_reminder": True,
    "create_po_draft": True,
    "request_quotation": True,
    "update_procurement_record": True,
    "schedule_escalation": True,
    "create_exception": True,
    "get_process_history": False,
    "get_task_history": False,
    "calculate_kpi": False,
}


def list_tool_capabilities() -> list[dict[str, Any]]:
    """Return registered tools with schemas and permission metadata."""
    out: list[dict[str, Any]] = []
    for tool in registry.list_tools():
        schema = tool.input_schema.model_json_schema()
        props = schema.get("properties") or {}
        required = schema.get("required") or []
        out.append(
            {
                "name": tool.name,
                "description": tool.description,
                "category": TOOL_CATEGORIES.get(tool.name, "General"),
                "permission_level": "standard",
                "requires_agent4_authorization": APPROVAL_REQUIRED.get(tool.name, True),
                "read_only": tool.name in READ_ONLY_TOOLS,
                "available": authorization.is_permitted(tool.name),
                "required_inputs": required,
                "input_fields": [
                    {
                        "name": k,
                        "type": (v.get("type") or "string"),
                        "description": v.get("description") or "",
                        "required": k in required,
                    }
                    for k, v in props.items()
                ],
            }
        )
    return sorted(out, key=lambda x: (x["category"], x["name"]))
