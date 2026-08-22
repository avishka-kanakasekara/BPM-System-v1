"""
Agent 2 — Reasoning Helpers

Assembles Gemini prompts for planning, email drafting, and the observe-replan loop.
"""

from typing import Any, Dict, List

from app.agent.context_engine import ProcessContext


def format_planning_context_prompt(
    context: ProcessContext, evidence: List[str], available_tools: List[str]
) -> str:
    """Format structured context and retrieved evidence into a Gemini planning prompt."""
    evidence_text = "\n".join([f"- {ev}" for ev in evidence]) if evidence else "- No historical evidence"
    tools_text = ", ".join(available_tools)

    return (
        f"TASK PLANNING CONTEXT:\n"
        f"Process Title: {context.process_title} (ID: {context.process_id})\n"
        f"Task Title: {context.task_title} (ID: {context.task_id})\n"
        f"Task Type: {context.task_type}\n"
        f"Assigned Role: {context.assigned_role} ({context.assigned_to})\n"
        f"Requester: {context.requester_email}\n"
        f"SLA Target: {context.sla_hours} hours | Elapsed: {context.elapsed_hours} hours\n"
        f"Priority: {context.priority} | Department: {context.department}\n"
        f"process_id: {context.process_id}\n"
        f"task_id: {context.task_id}\n\n"
        f"RETRIEVED HISTORICAL EVIDENCE:\n{evidence_text}\n\n"
        f"AVAILABLE TOOLSET:\n{tools_text}\n\n"
        f"Propose a structured ExecutionPlan that completes THIS task with the fewest allowed tools."
    )


def format_email_drafting_prompt(
    context: ProcessContext, purpose: str, recipient_role: str
) -> str:
    """Format structured context for Gemini email content drafting."""
    return (
        f"Recipient Role: {recipient_role}\n"
        f"Purpose: {purpose}\n"
        f"Process Title: {context.process_title} ({context.process_id})\n"
        f"Task Title: {context.task_title} ({context.task_id})\n"
        f"Elapsed Hours: {context.elapsed_hours} / SLA: {context.sla_hours} hours\n"
        f"Priority: {context.priority}\n"
        f"Draft professional email subject and body content."
    )


def format_loop_prompt(
    context: ProcessContext,
    objective: str,
    observations: List[Dict[str, Any]],
    remaining_tools: List[str],
) -> str:
    """Format observations for the post-ACT critic / next-step decision."""
    if observations:
        obs_lines = []
        for idx, item in enumerate(observations, start=1):
            obs_lines.append(
                f"{idx}. tool={item.get('tool')} status={item.get('status')} "
                f"error={item.get('error') or 'none'} result={item.get('result') or {}}"
            )
        obs_text = "\n".join(obs_lines)
    else:
        obs_text = "- No tools have run yet"

    return (
        f"ASSIGNED OBJECTIVE: {objective or context.task_title}\n"
        f"Process Title: {context.process_title} (process_id: {context.process_id})\n"
        f"Task Title: {context.task_title} (task_id: {context.task_id})\n"
        f"Task Type: {context.task_type}\n"
        f"Priority: {context.priority} | SLA: {context.elapsed_hours}h / {context.sla_hours}h\n\n"
        f"OBSERVATIONS:\n{obs_text}\n\n"
        f"REMAINING ALLOWED TOOLS: {', '.join(remaining_tools) or 'none'}\n\n"
        f"Decide COMPLETE, EXECUTE one more allowed tool, or ESCALATE. "
        f"If the last status is SUCCESS and it fulfills the objective, COMPLETE."
    )
