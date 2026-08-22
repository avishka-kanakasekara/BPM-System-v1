"""
Agent 2 — Top-Level Agent Cognitive Cycle Integration Tests

Tests Agent2.handle() end-to-end in Gemini offline mode:
1. Synthetic AgentMessage handling (e.g. send reminder / create PO draft).
2. Verifies returned response AgentMessage structure and EXECUTION_RESULT status.
3. Confirms non-empty PlanScoreBreakdown in payload evidence.
4. Verifies security rejection handling when forbidden actions are requested.
"""

import uuid
import pytest

from app.agents.agent2_execution.agent.agent import Agent2
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.llm.schemas import AgentMessage


@pytest.fixture
def agent2_offline():
    """Returns an Agent2 instance configured with Gemini offline stub client."""
    client = GeminiClient(is_offline=True)
    return Agent2(gemini_client=client)


# ---------------------------------------------------------------------------
# 1. Permitted Task Execution Test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent2_handle_permitted_task(agent2_offline):
    proc_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    msg = AgentMessage(
        message_id=f"msg-{uuid.uuid4().hex[:8]}",
        process_id=proc_id,
        trace_id="trace-test-001",
        sender="agent_4",
        receiver="agent_2",
        task_type="EXECUTE_TASK",
        payload={
            "task_id": task_id,
            "task_title": "Send Manager Reminder",
            "assigned_role": "manager",
            "assigned_to": "frank.miller@acmeglobal.com",
            "elapsed_hours": 18.5,
            "sla_hours": 24.0,
            "parameters": {
                "recipient": "frank.miller@acmeglobal.com",
                "subject": "Approval Reminder: Request #1001",
                "body": "Please review pending request #1001.",
                "process_id": proc_id,
                "task_id": task_id,
                "recipient_role": "manager",
            },
        },
        confidence=1.0,
        status="AUTHORIZED",
    )

    response = await agent2_offline.handle(msg, session=None)

    assert isinstance(response, AgentMessage)
    assert response.status == "EXECUTION_RESULT"
    assert response.sender == "agent_2"
    assert response.receiver == "agent_4"

    # Verify score breakdown in payload
    payload = response.payload
    assert "score_breakdown" in payload
    breakdown = payload["score_breakdown"]
    assert "safety" in breakdown
    assert "sla_suitability" in breakdown
    assert "reliability" in breakdown
    assert "efficiency" in breakdown
    assert "historical_success" in breakdown
    assert payload["total_score"] > 0.0
    assert "cognitive_trace" in payload
    assert payload["receipt_status"] in ["SUCCESS", "FAILED", "BLOCKED"]
    assert isinstance(payload.get("tools_executed"), list)


# ---------------------------------------------------------------------------
# 2. Forbidden Action Rejection Test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent2_handle_forbidden_action_blocked(agent2_offline):
    proc_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    # Message attempting unauthorized approve_payment
    msg = AgentMessage(
        message_id=f"msg-{uuid.uuid4().hex[:8]}",
        process_id=proc_id,
        trace_id="trace-test-002",
        sender="agent_4",
        receiver="agent_2",
        task_type="EXECUTE_TASK",
        payload={
            "task_id": task_id,
            "parameters": {
                "amount": 5000.00,
            },
        },
        confidence=1.0,
        status="AUTHORIZED",
    )

    # Force decision pipeline target tool to approve_payment via payload override
    msg.payload["parameters"]["tool_name"] = "approve_payment"

    response = await agent2_offline.handle(msg, session=None)

    assert isinstance(response, AgentMessage)
    assert response.payload["receipt_status"] in ["BLOCKED", "FAILED"]
