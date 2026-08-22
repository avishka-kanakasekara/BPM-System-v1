"""
Agent 2 — Top-Level Cognitive Cycle Orchestrator

Main entry point class Agent2 with handle(message: AgentMessage) -> AgentMessage method,
wiring all 11 nodes of the cognitive cycle (PERCEIVE through RECOMMEND/RECORD).

Enforces transparency requirement:
Logs every cognitive step (agent, model, action, reason, confidence) so decisions are fully reconstructible.
"""

import logging
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.agent.decision_engine import run_decision_pipeline
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.llm.schemas import AgentMessage

logger = logging.getLogger("agent_2.agent.orchestrator")


class Agent2:
    """
    Agent 2 — Intelligent Workflow Execution, RPA & Process Optimization Agent.
    """

    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        self.gemini_client = gemini_client or GeminiClient()

    async def handle(
        self, message: AgentMessage, session: Optional[AsyncSession] = None
    ) -> AgentMessage:
        """
        Handle an incoming inter-agent message by executing the 11-node cognitive cycle.

        :param message: Incoming AgentMessage
        :param session: Active AsyncSession (optional)
        :return: Outbound response AgentMessage with execution result & score breakdown
        """
        logger.info(
            f"COGNITIVE CYCLE START: message_id={message.message_id} | process_id={message.process_id} | sender={message.sender}"
        )

        # Execute 11-node decision engine pipeline
        receipt, score_breakdown = await run_decision_pipeline(
            message=message, session=session, gemini_client=self.gemini_client
        )

        response_status = "COMPLETED" if receipt.status == "SUCCESS" else "FAILED"
        if receipt.status == "BLOCKED":
            response_status = "REJECTED"

        response_payload = {
            "execution_receipt_id": str(receipt.id),
            "tool_name": receipt.tool_name,
            "action": receipt.action,
            "receipt_status": receipt.status,
            "attempt_number": receipt.attempt_number,
            "latency_ms": receipt.latency_ms,
            "score_breakdown": score_breakdown.details,
            "total_score": score_breakdown.total_score,
            "error_message": receipt.error_message or "",
            "cognitive_trace": score_breakdown.details.get("cognitive_trace", []),
            "tools_executed": score_breakdown.details.get("tools_executed", []),
            "critic_notes": score_breakdown.details.get("critic_notes", ""),
        }

        outbound_message = AgentMessage(
            message_id=f"msg-resp-{uuid.uuid4().hex[:8]}",
            process_id=message.process_id,
            trace_id=message.trace_id or f"trace-{uuid.uuid4().hex[:8]}",
            sender="agent_2",
            receiver=message.sender or "agent_4",
            task_type="EXECUTION_RESULT",
            payload=response_payload,
            evidence_refs=[str(receipt.id)],
            confidence=round(score_breakdown.total_score, 2),
            status="EXECUTION_RESULT",
        )

        logger.info(
            f"COGNITIVE CYCLE COMPLETE: status={outbound_message.status} | score={score_breakdown.total_score} | receipt_status={receipt.status}"
        )
        return outbound_message
