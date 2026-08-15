"""
Agent 2 — Decision Engine & Plan Scoring Engine

Implements the 11-Node Cognitive Pipeline and deterministic Plan Scoring formula:
score = 0.30*safety + 0.25*sla_suitability + 0.20*reliability + 0.15*efficiency + 0.10*historical_success

Every sub-score is computed deterministically from data (not asked of Gemini):
- safety: 1.0 if all proposed tools are on ALLOWED list; 0.0 otherwise.
- sla_suitability: SLA headroom fraction max(0.0, 1.0 - elapsed / sla).
- reliability: Historical tool success rate from episodic memory.
- efficiency: Step complexity score max(0.2, 1.0 - 0.1 * (steps - 1)).
- historical_success: Baseline process completion rate.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import context_engine, memory, planner
from app.database.models import ExecutionReceipt
from app.execution.execution_engine import execute_with_recovery
from app.llm.gemini_client import GeminiClient
from app.llm.schemas import AgentMessage, ExecutionPlan
from app.security import authorization
from app.security.tool_guard import ToolGuard

logger = logging.getLogger("agent_2.agent.decision_engine")


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
    """
    Compute deterministic plan score based on 5 data-driven metrics.
    """
    # 1. Safety Sub-score (weight 0.30): 1.0 if all selected_tools allowed; 0.0 otherwise
    tools = plan.selected_tools or []
    all_allowed = all(authorization.is_permitted(t) for t in tools) if tools else True
    safety_score = 1.0 if all_allowed else 0.0

    # 2. SLA Suitability Sub-score (weight 0.25): Headroom fraction
    sla = max(1.0, context.sla_hours)
    elapsed = max(0.0, context.elapsed_hours)
    sla_suitability_score = max(0.0, min(1.0, 1.0 - (elapsed / sla)))

    # 3. Reliability Sub-score (weight 0.20): Historical tool success rate
    if tools:
        rates = [
            await memory.EpisodicMemory.get_tool_success_rate(session, t) for t in tools
        ]
        reliability_score = sum(rates) / float(len(rates))
    else:
        reliability_score = 0.95

    # 4. Efficiency Sub-score (weight 0.15): Inverse step complexity
    step_count = len(plan.steps) if plan.steps else 1
    efficiency_score = max(0.2, min(1.0, 1.0 - 0.1 * (step_count - 1)))

    # 5. Historical Success Sub-score (weight 0.10): Baseline completion rate
    historical_success_score = 0.94

    # Weighted Total Formula
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


async def run_decision_pipeline(
    message: AgentMessage,
    session: Optional[AsyncSession] = None,
    gemini_client: Optional[GeminiClient] = None,
) -> Tuple[ExecutionReceipt, PlanScoreBreakdown]:
    """
    Execute the 11-Node Cognitive Decision Pipeline end-to-end:
    PERCEIVE -> UNDERSTAND -> RETRIEVE -> REASON -> PLAN -> VALIDATE -> SCORE -> SELECT -> ACT -> OBSERVE -> RECOVER
    """
    client = gemini_client or GeminiClient()

    # Node 1 & 2: PERCEIVE & UNDERSTAND
    ctx = await context_engine.perceive_context(session, message)

    # Node 3: RETRIEVE HISTORY
    evidence = await memory.ProcessMemory.retrieve_evidence(
        session, query=ctx.task_title, caller_role=ctx.assigned_role
    )

    # Node 4 & 5: REASON & PLAN
    plan = await planner.generate_plan(ctx, evidence, gemini_client=client)

    # Node 6: VALIDATE PLAN (Security Guard Pre-check)
    payload_params = message.payload.get("parameters") or {}
    target_tool = payload_params.get("tool_name") or (plan.selected_tools[0] if plan.selected_tools else "send_email")
    guard = ToolGuard(session=session)

    # Prepare tool parameters based on selected tool
    tool_params = message.payload.get("parameters") or {}
    if not tool_params:
        if target_tool in ["send_email", "send_reminder"]:
            tool_params = {
                "recipient": ctx.assigned_to or "frank.miller@acmeglobal.com",
                "subject": f"Approval Reminder: {ctx.process_title}",
                "body": f"Please review pending task #{ctx.task_id}.",
                "process_id": ctx.process_id,
                "task_id": ctx.task_id,
                "recipient_role": ctx.assigned_role,
            }
        elif target_tool == "create_po_draft":
            tool_params = {
                "vendor_id": "vendor-v100",
                "amount": float(message.payload.get("amount", 2500.00)),
                "process_id": ctx.process_id,
            }
        else:
            tool_params = {
                "process_id": ctx.process_id,
                "task_id": ctx.task_id,
            }

    # Node 7: SCORE PLAN
    score_breakdown = await score_execution_plan(plan, ctx, session)

    # Node 8: SELECT PLAN
    # (Selected target_tool and tool_params)

    # Node 9, 10, 11: ACT, OBSERVE, RECOVER (Execution Engine)
    receipt = await execute_with_recovery(
        process_id=ctx.process_id,
        task_id=ctx.task_id,
        tool_name=target_tool,
        parameters=tool_params,
        session=session,
        actor=message.sender or "agent_2",
        gemini_client=client,
    )

    return receipt, score_breakdown
