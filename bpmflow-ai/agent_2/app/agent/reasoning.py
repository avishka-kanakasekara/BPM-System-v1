"""
Agent 2 — Reasoning Helpers

Provides DRY helper functions for assembling Gemini prompts and parsing structured responses.
"""

from typing import Any, Dict, List, Optional
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
        f"SLA Target: {context.sla_hours} hours | Elapsed: {context.elapsed_hours} hours\n"
        f"Priority: {context.priority} | Department: {context.department}\n\n"
        f"RETRIEVED HISTORICAL EVIDENCE:\n{evidence_text}\n\n"
        f"AVAILABLE TOOLSET:\n{tools_text}\n\n"
        f"Propose a structured ExecutionPlan for achieving the task objective safely."
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
