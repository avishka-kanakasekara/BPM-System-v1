"""
Agent 2 — Planner (REASON + PLAN Nodes 4 & 5)

Assembles process context, retrieved memory evidence, and available tool declarations into a Gemini call,
returning a structured ExecutionPlan object.
"""

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context_engine import ProcessContext
from app.agent.reasoning import format_planning_context_prompt
from app.database.ids import parse_uuid
from app.database.models import ExecutionPlan as ExecutionPlanRow
from app.database.persistence import ensure_process_instance
from app.llm import prompts
from app.llm.gemini_client import GeminiClient
from app.llm.schemas import ExecutionPlan
from app.tools import registry


async def generate_plan(
    context: ProcessContext,
    evidence: List[str],
    gemini_client: Optional[GeminiClient] = None,
    session: Optional[AsyncSession] = None,
) -> ExecutionPlan:
    """
    REASON & PLAN: Call Gemini to generate a structured ExecutionPlan.

    :param context: ProcessContext object
    :param evidence: List of evidence strings from hybrid memory retrieval
    :param gemini_client: Optional GeminiClient instance
    :return: ExecutionPlan Pydantic model instance
    """
    client = gemini_client or GeminiClient()
    available_tools = [t.name for t in registry.list_tools()]

    prompt_text = format_planning_context_prompt(context, evidence, available_tools)

    plan = await client.generate_structured_output(
        prompt=prompt_text,
        response_schema=ExecutionPlan,
        system_instruction=prompts.SYSTEM_PROMPT_PLANNING,
        model_tier="pro",
    )
    if plan.task_id in {"", "task-offline", "task-stub-101"}:
        plan = plan.model_copy(update={"task_id": context.task_id})

    if session is not None:
        try:
            await ensure_process_instance(
                session,
                context.process_id,
                title=context.process_title,
                process_type=context.process_type,
                department=context.department,
            )
            session.add(
                ExecutionPlanRow(
                    process_instance_id=parse_uuid(context.process_id),
                    status="SELECTED",
                    plan_json=plan.model_dump(),
                    reasoning=plan.reasoning_summary,
                )
            )
            await session.commit()
        except Exception:
            try:
                await session.rollback()
            except Exception:
                pass
    return plan
