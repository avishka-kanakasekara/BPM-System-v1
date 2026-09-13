"""Named cognitive pipeline nodes with explicit input/output contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.agent import context_engine, memory, planner
from app.agents.agent2_execution.agent.context_engine import ProcessContext
from app.agents.agent2_execution.agent.planner_fallback import (
    PlanValidationError,
    FullWorkflowForbidden,
    build_deterministic_plan,
    is_full_task_suite,
    validate_execution_plan,
)
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.llm.schemas import (
    AgentMessage,
    ExecutionPlan,
)


@dataclass(frozen=True)
class CognitiveNode:
    """One inspectable step in the Agent 2 cognitive cycle."""

    name: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    handler: str


COGNITIVE_NODES: tuple[CognitiveNode, ...] = (
    CognitiveNode("PERCEIVE", ("AgentMessage",), ("ProcessContext",), "context_engine.perceive_context"),
    CognitiveNode("RETRIEVE", ("ProcessContext",), ("evidence: List[str]",), "memory.ProcessMemory.retrieve_evidence"),
    CognitiveNode("REASON", ("ProcessContext", "evidence"), ("AgentDecision",), "decision_engine._reason_about_task"),
    CognitiveNode("PLAN", ("ProcessContext", "evidence"), ("ExecutionPlan",), "planner.generate_plan"),
    CognitiveNode("SCORE", ("ExecutionPlan", "ProcessContext"), ("PlanScoreBreakdown",), "decision_engine.score_execution_plan"),
    CognitiveNode("ACT", ("tool_name", "parameters"), ("ExecutionReceipt",), "execution_engine.execute_with_recovery"),
    CognitiveNode("OBSERVE", ("ExecutionReceipt",), ("observation: dict",), "decision_engine._observation_from_receipt"),
    CognitiveNode("REPLAN", ("observations",), ("CycleStepDecision",), "decision_engine._decide_next_step"),
    CognitiveNode("LEARN", ("ExecutionReceipt",), ("kpi_snapshot",), "kpi_engine.compute_and_save_kpis"),
    CognitiveNode("OPTIMIZE", ("process_id",), ("OptimizationRecommendation",), "recommendation_engine.generate_optimization_proposal"),
    CognitiveNode("RECORD", ("ExecutionReceipt",), ("AgentMessage",), "agent.Agent2.handle"),
)


async def perceive(message: AgentMessage, session: AsyncSession | None) -> ProcessContext:
    return await context_engine.perceive_context(session, message)


async def retrieve(
    session: AsyncSession | None,
    context: ProcessContext,
) -> list[str]:
    return await memory.ProcessMemory.retrieve_evidence(
        session,
        query=context.task_title,
        caller_role=context.assigned_role,
        process_id=context.process_id,
    )


async def plan_with_validation(
    context: ProcessContext,
    evidence: list[str],
    *,
    gemini_client: GeminiClient | None = None,
    session: AsyncSession | None = None,
    tool_override: str | None = None,
) -> ExecutionPlan:
    """PLAN node: LLM plan with deterministic offline fallback; never returns empty tools."""
    client = gemini_client or GeminiClient()
    if is_full_task_suite(tool_override):
        raise FullWorkflowForbidden(
            "FULL_WORKFLOW_EXECUTION_FORBIDDEN: Agent 2 executes one WorkflowStep only"
        )
    try:
        if client.is_offline:
            plan = build_deterministic_plan(context, evidence, tool_override=tool_override)
        else:
            plan = await planner.generate_plan(context, evidence, gemini_client=client, session=session)
        return validate_execution_plan(plan)
    except PlanValidationError:
        raise
    except Exception:
        plan = build_deterministic_plan(context, evidence, tool_override=tool_override)
        return validate_execution_plan(plan)


def node_catalog() -> list[dict[str, Any]]:
    """Return pipeline node metadata for tests and diagnostics."""
    return [
        {
            "name": node.name,
            "inputs": list(node.inputs),
            "outputs": list(node.outputs),
            "handler": node.handler,
        }
        for node in COGNITIVE_NODES
    ]
