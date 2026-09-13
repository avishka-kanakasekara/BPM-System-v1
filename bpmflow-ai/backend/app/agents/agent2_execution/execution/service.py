"""
Agent 2 — Authorized execution service.

Routes UI/API execution requests through the full cognitive pipeline.
There is no direct Frontend → tool handler path.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.agent.agent import Agent2
from app.agents.agent2_execution.agent.decision_engine import PlanScoreBreakdown
from app.agents.agent2_execution.database.models import ExecutionReceipt
from app.agents.agent2_execution.execution.idempotency import generate_idempotency_key
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.llm.schemas import AgentMessage
from app.agents.agent2_execution.security.trace_sanitizer import sanitize_execution_explanation

logger = logging.getLogger("agent_2.execution.service")


def _build_authorized_message(
    *,
    process_id: str,
    task_id: str,
    tool_name: str,
    parameters: dict[str, Any],
    correlation_id: str = "",
    actor: str = "agent_4",
) -> AgentMessage:
    """Build an AUTHORIZED inter-agent message after server-side stage validation."""
    params = dict(parameters)
    params.setdefault("process_id", process_id)
    params.setdefault("task_id", task_id)
    params["tool_name"] = tool_name
    return AgentMessage(
        message_id=f"msg-exec-{uuid.uuid4().hex[:10]}",
        process_id=process_id,
        trace_id=correlation_id or f"trace-{uuid.uuid4().hex[:10]}",
        sender=actor,
        receiver="agent_2",
        task_type="EXECUTE_TASK",
        payload={
            "task_id": task_id,
            "parameters": params,
            **params,
        },
        evidence_refs=[],
        confidence=1.0,
        status="AUTHORIZED",
    )


async def run_authorized_pipeline(
    *,
    process_id: str,
    task_id: str,
    tool_name: str,
    parameters: dict[str, Any],
    session: AsyncSession | None = None,
    correlation_id: str = "",
    actor: str = "agent_4",
    idempotency_key: str | None = None,
    gemini_client: GeminiClient | None = None,
) -> tuple[ExecutionReceipt, PlanScoreBreakdown, dict[str, Any]]:
    """
    Execute through Agent 2 cognitive pipeline (PERCEIVE → … → ACT → OBSERVE).

    Tool Guard and idempotency remain enforced inside execute_with_recovery during ACT.
    """
    message = _build_authorized_message(
        process_id=process_id,
        task_id=task_id,
        tool_name=tool_name,
        parameters=parameters,
        correlation_id=correlation_id,
        actor=actor,
    )
    if idempotency_key:
        message.payload["idempotency_key"] = idempotency_key

    agent = Agent2(gemini_client=gemini_client or GeminiClient())
    response = await agent.handle(message, session=session)

    payload = dict(response.payload or {})
    receipt_id = payload.get("execution_receipt_id") or ""
    score_details = payload.get("score_breakdown") or {}
    explanation = sanitize_execution_explanation(
        {
            "receipt_status": payload.get("receipt_status"),
            "tool_name": payload.get("tool_name"),
            "decision_reason": score_details.get("decision_reason"),
            "plan_reasoning": score_details.get("plan_reasoning"),
            "tools_executed": payload.get("tools_executed") or score_details.get("tools_executed"),
            "critic_notes": payload.get("critic_notes") or score_details.get("critic_notes"),
            "execution_events": score_details.get("cognitive_trace"),
            "total_score": payload.get("total_score"),
            "score_breakdown": {
                k: v
                for k, v in score_details.items()
                if k
                in {
                    "safety",
                    "sla_suitability",
                    "reliability",
                    "efficiency",
                    "historical_success",
                    "total_score",
                    "decision",
                    "decision_reason",
                    "plan_reasoning",
                    "working_state",
                }
            },
        }
    )

    # Reconstruct receipt from pipeline response when ORM row unavailable
    from datetime import datetime

    receipt = ExecutionReceipt(
        id=uuid.UUID(receipt_id) if receipt_id else uuid.uuid4(),
        process_id=uuid.UUID(process_id),
        task_id=uuid.UUID(task_id),
        agent_id=actor,
        tool_name=payload.get("tool_name") or tool_name,
        action=payload.get("action") or tool_name,
        attempt_number=int(payload.get("attempt_number") or 1),
        idempotency_key=idempotency_key
        or generate_idempotency_key(process_id, task_id, tool_name),
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        status=str(payload.get("receipt_status") or "FAILED"),
        result={"plan_score": explanation.get("score_breakdown", {})},
        error_message=payload.get("error_message") or "",
        latency_ms=int(payload.get("latency_ms") or 0),
    )

    score = PlanScoreBreakdown(
        total_score=float(payload.get("total_score") or 0.0),
        safety=float((payload.get("score_breakdown") or {}).get("safety") or 0.0),
        sla_suitability=float((payload.get("score_breakdown") or {}).get("sla_suitability") or 0.0),
        reliability=float((payload.get("score_breakdown") or {}).get("reliability") or 0.0),
        efficiency=float((payload.get("score_breakdown") or {}).get("efficiency") or 0.0),
        historical_success=float((payload.get("score_breakdown") or {}).get("historical_success") or 0.0),
        details=payload.get("score_breakdown") or {},
    )
    return receipt, score, explanation
