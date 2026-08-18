"""
Agent 2 — Decision Engine & Plan Scoring Engine

Implements the 11-Node Cognitive Pipeline and deterministic Plan Scoring formula:
score = 0.30*safety + 0.25*sla_suitability + 0.20*reliability + 0.15*efficiency + 0.10*historical_success
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import context_engine, memory, planner
from app.database.models import ExecutionReceipt
from app.database.persistence import ensure_process_instance, ensure_task
from app.execution.execution_engine import execute_with_recovery
from app.llm import function_declarations, prompts
from app.llm.gemini_client import GeminiClient
from app.llm.schemas import AgentDecision, AgentMessage, ExecutionPlan
from app.optimization import recommendation_engine
from app.security import authorization
from app.tools.registry import registry

logger = logging.getLogger("agent_2.agent.decision_engine")

MAX_PLAN_TOOLS = 5


@dataclass
class PlanScoreBreakdown:
    total_score: float
    safety: float
    sla_suitability: float
    reliability: float
    efficiency: float
    historical_success: float
    details: Dict[str, Any] = field(default_factory=dict)


async def score_execution_plan(
    plan: ExecutionPlan,
    context: context_engine.ProcessContext,
    session: Optional[AsyncSession] = None,
) -> PlanScoreBreakdown:
    """Compute deterministic plan score based on 5 data-driven metrics."""
    tools = plan.selected_tools or []
    all_allowed = all(authorization.is_permitted(t) for t in tools) if tools else True
    safety_score = 1.0 if all_allowed else 0.0

    sla = max(1.0, context.sla_hours)
    elapsed = max(0.0, context.elapsed_hours)
    sla_suitability_score = max(0.0, min(1.0, 1.0 - (elapsed / sla)))

    if tools:
        rates = [
            await memory.EpisodicMemory.get_tool_success_rate(session, t) for t in tools
        ]
        reliability_score = sum(rates) / float(len(rates))
        historical_success_score = reliability_score
    else:
        reliability_score = 0.95
        historical_success_score = 0.95

    step_count = len(plan.steps) if plan.steps else 1
    efficiency_score = max(0.2, min(1.0, 1.0 - 0.1 * (step_count - 1)))

    total_score = round(
        0.30 * safety_score
        + 0.25 * sla_suitability_score
        + 0.20 * reliability_score
        + 0.15 * efficiency_score
        + 0.10 * historical_success_score,
        4,
    )

    details = {
        "safety": round(safety_score, 4),
        "sla_suitability": round(sla_suitability_score, 4),
        "reliability": round(reliability_score, 4),
        "efficiency": round(efficiency_score, 4),
        "historical_success": round(historical_success_score, 4),
        "total_score": total_score,
    }

    logger.info(f"PLAN SCORE BREAKDOWN: total={total_score} | details={details}")
    return PlanScoreBreakdown(
        total_score=total_score,
        safety=safety_score,
        sla_suitability=sla_suitability_score,
        reliability=reliability_score,
        efficiency=efficiency_score,
        historical_success=historical_success_score,
        details=details,
    )


def _context_defaults(ctx: context_engine.ProcessContext) -> Dict[str, Any]:
    return {
        "process_id": ctx.process_id,
        "task_id": ctx.task_id,
        "recipient": ctx.assigned_to or ctx.requester_email,
        "recipient_role": ctx.assigned_role or "manager",
        "elapsed_hours": ctx.elapsed_hours,
        "sla_hours": ctx.sla_hours or 24.0,
        "assigned_role": ctx.assigned_role,
        "assigned_to": ctx.assigned_to,
        "priority": ctx.priority,
        "process_type": ctx.process_type or "procurement",
        "title": ctx.task_title or "Workflow task",
        "task_type": ctx.task_type or "AUTOMATED",
        "subject": f"{ctx.task_title or 'Task update'}: {ctx.process_title}",
        "body": (
            f"Please action '{ctx.task_title}' for process '{ctx.process_title}'. "
            f"Elapsed {ctx.elapsed_hours}h / SLA {ctx.sla_hours}h. Priority: {ctx.priority}."
        ),
    }


async def _build_tool_params(
    target_tool: str,
    incoming_tool_params: Dict[str, Any],
    ctx: context_engine.ProcessContext,
    client: GeminiClient,
) -> Dict[str, Any]:
    tool_def = registry.get(target_tool)
    merged = dict(_context_defaults(ctx))
    merged.update({k: v for k, v in incoming_tool_params.items() if v not in (None, "")})

    if tool_def is not None:
        try:
            validated = tool_def.input_schema.model_validate(merged)
            return validated.model_dump()
        except Exception:
            try:
                validated = tool_def.input_schema.model_validate(incoming_tool_params)
                return validated.model_dump()
            except Exception:
                pass

        tool_decl = function_declarations.get_tool_declaration_by_name(target_tool)
        if tool_decl:
            fc = await client.generate_function_call(
                prompt=(
                    "Generate ONLY tool-call parameters for Agent 2. "
                    "Fill every required field from process context. Never invent forbidden actions.\n\n"
                    f"Process Context:\n"
                    f"- process_id: {ctx.process_id}\n"
                    f"- task_id: {ctx.task_id}\n"
                    f"- process_title: {ctx.process_title}\n"
                    f"- task_title: {ctx.task_title}\n"
                    f"- assigned_role: {ctx.assigned_role}\n"
                    f"- assigned_to: {ctx.assigned_to}\n"
                    f"- requester_email: {ctx.requester_email}\n"
                    f"- priority: {ctx.priority}\n"
                    f"- sla_hours: {ctx.sla_hours}\n"
                    f"- elapsed_hours: {ctx.elapsed_hours}\n"
                    f"- department: {ctx.department}\n"
                    f"- metadata: {ctx.metadata}\n\n"
                    f"Incoming payload parameters (may be incomplete): {incoming_tool_params}\n"
                    f"Target tool: {target_tool}\n"
                ),
                tools=[tool_decl],
                model_tier="flash",
            )
            if fc.name.strip().lower() == target_tool.strip().lower():
                proposed = dict(merged)
                proposed.update(fc.parameters or {})
                try:
                    return tool_def.input_schema.model_validate(proposed).model_dump()
                except Exception:
                    return proposed

    return dict(incoming_tool_params) or merged


def _matching_tools(incoming_tool_params: Dict[str, Any]) -> List[str]:
    matched: List[str] = []
    if not incoming_tool_params:
        return matched
    for tool in registry.list_tools():
        try:
            tool.input_schema.model_validate(incoming_tool_params)
            matched.append(tool.name)
        except Exception:
            continue
    return matched


def _select_tools_to_run(
    plan: ExecutionPlan,
    tool_name_override: Optional[str],
    incoming_tool_params: Dict[str, Any],
    reasoned_tool: Optional[str] = None,
) -> List[str]:
    if tool_name_override:
        return [tool_name_override]

    matching = _matching_tools(incoming_tool_params)
    planned = [t for t in (plan.selected_tools or []) if t]
    if reasoned_tool:
        planned = [reasoned_tool] + [t for t in planned if t != reasoned_tool]
    if matching:
        intersection = [t for t in planned if t in matching]
        if reasoned_tool and reasoned_tool in matching:
            return [reasoned_tool]
        return (intersection or matching)[:MAX_PLAN_TOOLS]

    permitted = [t for t in planned if authorization.is_permitted(t)]
    if permitted:
        return permitted[:MAX_PLAN_TOOLS]
    return [planned[0]] if planned else ["send_email"]


async def _reason_about_task(
    ctx: context_engine.ProcessContext,
    evidence: List[str],
    client: GeminiClient,
) -> AgentDecision:
    available_tools = [t.name for t in registry.list_tools()]
    prompt = (
        f"Decide how to execute this workflow task.\n"
        f"Process: {ctx.process_title} ({ctx.process_id})\n"
        f"Task: {ctx.task_title} ({ctx.task_id})\n"
        f"Task type: {ctx.task_type}\n"
        f"Assigned: {ctx.assigned_role} / {ctx.assigned_to}\n"
        f"Requester: {ctx.requester_email}\n"
        f"Priority: {ctx.priority}\n"
        f"SLA: {ctx.elapsed_hours}h elapsed / {ctx.sla_hours}h\n"
        f"Department: {ctx.department}\n"
        f"Metadata: {ctx.metadata}\n"
        f"Evidence:\n" + ("\n".join(f"- {item}" for item in evidence) or "- none") + "\n"
        f"Allowed tools: {', '.join(available_tools)}\n"
    )
    return await client.generate_structured_output(
        prompt=prompt,
        response_schema=AgentDecision,
        system_instruction=prompts.SYSTEM_PROMPT_REASONING,
        model_tier="pro",
    )


async def run_decision_pipeline(
    message: AgentMessage,
    session: Optional[AsyncSession] = None,
    gemini_client: Optional[GeminiClient] = None,
) -> Tuple[ExecutionReceipt, PlanScoreBreakdown]:
    """
    Execute the 11-Node Cognitive Decision Pipeline end-to-end:
    PERCEIVE -> UNDERSTAND -> RETRIEVE -> REASON -> PLAN -> VALIDATE -> SCORE -> SELECT -> ACT -> OBSERVE -> RECOVER
    plus LEARN / OPTIMIZE / RECOMMEND when the task is analytical.
    """
    client = gemini_client or GeminiClient()

    ctx = await context_engine.perceive_context(session, message)
    if session is not None:
        await ensure_process_instance(
            session,
            ctx.process_id,
            title=ctx.process_title,
            process_type=ctx.process_type,
            department=ctx.department,
            requester_email=ctx.requester_email,
            metadata={"trace_id": message.trace_id, "message_id": message.message_id},
        )
        await ensure_task(
            session,
            ctx.process_id,
            ctx.task_id,
            title=ctx.task_title,
            task_type=ctx.task_type,
            assigned_role=ctx.assigned_role,
            assigned_to=ctx.assigned_to,
            sla_hours=ctx.sla_hours,
            priority=ctx.priority,
        )

    evidence = await memory.ProcessMemory.retrieve_evidence(
        session, query=ctx.task_title, caller_role=ctx.assigned_role
    )
    decision = await _reason_about_task(ctx, evidence, client)
    plan = await planner.generate_plan(ctx, evidence, gemini_client=client, session=session)

    payload_params = message.payload.get("parameters") or {}
    tool_name_override = payload_params.get("tool_name")
    incoming_tool_params = {k: v for k, v in payload_params.items() if k != "tool_name"}
    if decision.parameters:
        merged_params = dict(decision.parameters)
        merged_params.update({k: v for k, v in incoming_tool_params.items() if v not in (None, "")})
        incoming_tool_params = merged_params

    reasoned_tool = decision.selected_tool if decision.decision == "EXECUTE" else None
    tools_to_run = _select_tools_to_run(
        plan, tool_name_override, incoming_tool_params, reasoned_tool=reasoned_tool
    )
    plan_for_scoring = plan.model_copy(update={"selected_tools": tools_to_run or plan.selected_tools})
    score_breakdown = await score_execution_plan(plan_for_scoring, ctx, session)
    score_breakdown.details["decision"] = decision.decision
    score_breakdown.details["decision_reason"] = decision.reason
    score_breakdown.details["plan_reasoning"] = plan.reasoning_summary

    last_receipt: Optional[ExecutionReceipt] = None
    for tool_name in tools_to_run:
        tool_params = await _build_tool_params(tool_name, incoming_tool_params, ctx, client)
        last_receipt = await execute_with_recovery(
            process_id=ctx.process_id,
            task_id=ctx.task_id,
            tool_name=tool_name,
            parameters=tool_params,
            session=session,
            actor=message.sender or "agent_2",
            gemini_client=client,
        )
        logger.info(
            f"ACT complete: tool={tool_name} status={last_receipt.status} score={score_breakdown.total_score}"
        )
        if last_receipt.status == "BLOCKED":
            break

    if last_receipt is None:
        last_receipt = await execute_with_recovery(
            process_id=ctx.process_id,
            task_id=ctx.task_id,
            tool_name="create_exception",
            parameters={
                "process_id": ctx.process_id,
                "task_id": ctx.task_id,
                "severity": "MEDIUM",
                "reason": "No executable tool could be selected from the plan",
            },
            session=session,
            actor=message.sender or "agent_2",
            gemini_client=client,
        )

    analytical = any(
        t in {"calculate_kpi", "get_process_history", "get_task_history"} for t in tools_to_run
    ) or str(message.task_type).upper() in {"ANALYZE", "OPTIMIZE", "GENERATE_RECOMMENDATION"}
    if session is not None and last_receipt.status == "SUCCESS":
        try:
            from app.analytics import kpi_engine

            await kpi_engine.compute_and_save_kpis(session, process_id=ctx.process_id)
        except Exception as exc:
            logger.warning(f"LEARN KPI snapshot failed: {exc}")
    if analytical and last_receipt.status == "SUCCESS":
        try:
            rec = await recommendation_engine.generate_optimization_proposal(
                session, process_id=ctx.process_id, gemini_client=client
            )
            score_breakdown.details["recommendation_id"] = rec.id
            score_breakdown.details["recommendation_status"] = rec.status
        except Exception as exc:
            logger.warning(f"Optimization recommendation generation failed: {exc}")

    return last_receipt, score_breakdown
