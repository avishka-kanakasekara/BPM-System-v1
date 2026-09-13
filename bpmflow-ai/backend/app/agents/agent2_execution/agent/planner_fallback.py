"""Deterministic offline planner fallback for Agent 2."""

from __future__ import annotations

from app.agents.agent2_execution.agent.context_engine import ProcessContext
from app.agents.agent2_execution.llm.schemas import ExecutionPlan
from app.agents.agent2_execution.security import authorization

# Sentinel used by Agent 4 dispatch and the Tools UI to run every registered tool once.
FULL_TASK_SUITE_TOOL = "__full_task_suite__"

# Ordered procurement workflow verification suite (Step 5 checklist).
FULL_TASK_SUITE_TOOLS: tuple[str, ...] = (
    "create_po_draft",
    "request_quotation",
    "update_procurement_record",
    "create_workflow_task",
    "update_task",
    "send_email",
    "send_reminder",
    "schedule_escalation",
    "create_exception",
    "get_process_history",
    "get_task_history",
    "calculate_kpi",
)


class PlanValidationError(ValueError):
    """Raised when an execution plan is empty or invalid."""


def is_full_task_suite(tool_name: str | None) -> bool:
    return (tool_name or "").strip().lower() == FULL_TASK_SUITE_TOOL


class FullWorkflowForbidden(PlanValidationError):
    error_code = "FULL_WORKFLOW_EXECUTION_FORBIDDEN"


def _infer_tools_from_context(
    context: ProcessContext,
    *,
    tool_override: str | None = None,
) -> list[str]:
    if is_full_task_suite(tool_override):
        raise FullWorkflowForbidden(
            "FULL_WORKFLOW_EXECUTION_FORBIDDEN: Agent 2 executes one WorkflowStep only"
        )

    if tool_override and authorization.is_permitted(tool_override):
        return [tool_override.strip().lower()]

    proc = (context.process_type or "").lower()
    task = (context.task_type or context.task_title or "").lower()

    if "remind" in task or "sla" in task:
        return ["send_reminder"]
    if "escalat" in task:
        return ["schedule_escalation"]
    if "quot" in task or "rfq" in task:
        return ["request_quotation"]
    if "kpi" in task or "metric" in task:
        return ["calculate_kpi"]
    if "history" in task:
        return ["get_process_history"]
    if "procur" in proc or "purchase" in proc or "po" in task:
        return ["create_po_draft"]
    if "email" in task or "notify" in task:
        return ["send_email"]

    return ["create_workflow_task"]


def build_deterministic_plan(
    context: ProcessContext,
    evidence: list[str],
    *,
    tool_override: str | None = None,
) -> ExecutionPlan:
    """Build a schema-valid plan without LLM when offline or LLM fails."""
    tools = [
        t
        for t in _infer_tools_from_context(context, tool_override=tool_override)
        if authorization.is_permitted(t)
    ]
    if not tools:
        raise PlanValidationError(
            "Deterministic planner could not select any permitted tools for this task"
        )

    objective = context.task_title or "Execute assigned workflow task"
    if evidence:
        objective = f"{objective} (evidence items: {len(evidence)})"

    steps = [f"Execute {tool}" for tool in tools]
    return ExecutionPlan(
        task_id=context.task_id,
        objective=objective,
        steps=steps,
        selected_tools=tools,
        reasoning_summary=(
            "Deterministic offline plan derived from process/task context "
            f"with tools: {', '.join(tools)}"
        ),
        risk_level="LOW",
        confidence=0.85,
        fallback_strategy="Escalate to assigned manager if primary tool fails",
        requires_human=False,
    )


def validate_execution_plan(plan: ExecutionPlan) -> ExecutionPlan:
    """Ensure plan has schema-valid, non-empty tool selection."""
    tools = [t.strip().lower() for t in (plan.selected_tools or []) if t and t.strip()]
    steps = [s.strip() for s in (plan.steps or []) if s and s.strip()]

    if not tools:
        raise PlanValidationError("Execution plan must include at least one selected tool")
    if not steps:
        raise PlanValidationError("Execution plan must include at least one step")
    if not (plan.objective or "").strip():
        raise PlanValidationError("Execution plan must include a non-empty objective")

    for tool in tools:
        if not authorization.is_permitted(tool):
            raise PlanValidationError(f"Plan references forbidden tool {tool!r}")

    return plan.model_copy(update={"selected_tools": tools, "steps": steps})
