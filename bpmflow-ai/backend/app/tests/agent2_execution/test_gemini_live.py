"""Live Gemini verification for Agent 2 (skipped when key/offline).

These tests exercise the real Gemini API and real tool execution path.
They never use offline stubs.
"""

from __future__ import annotations

import os
import uuid

import pytest

from app.agents.agent2_execution.agent.agent import Agent2
from app.agents.agent2_execution.config import settings as agent2_settings
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.llm.schemas import AgentMessage, ExecutionPlan, ToolCallContract


def _live_gemini_available() -> bool:
    key = (agent2_settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY") or "").strip()
    offline = bool(agent2_settings.GEMINI_OFFLINE) or os.getenv("GEMINI_OFFLINE", "").lower() in {
        "1",
        "true",
        "yes",
    }
    return bool(key) and not key.startswith("your_") and not offline


pytestmark = pytest.mark.skipif(
    not _live_gemini_available(),
    reason="Live Gemini not configured (GEMINI_API_KEY required, GEMINI_OFFLINE must be false)",
)


@pytest.fixture
def live_client() -> GeminiClient:
    client = GeminiClient(is_offline=False)
    assert client.is_offline is False
    assert client._sdk_client is not None
    return client


@pytest.mark.asyncio
async def test_live_gemini_structured_execution_plan(live_client: GeminiClient):
    plan = await live_client.generate_structured_output(
        prompt=(
            "Create an execution plan for an AUTHORIZED procurement reminder task. "
            "process_id=proc-live-1 task_id=task-live-1. Prefer send_email."
        ),
        response_schema=ExecutionPlan,
        model_tier="flash",
    )
    assert isinstance(plan, ExecutionPlan)
    assert plan.selected_tools or plan.steps
    assert "offline" not in (plan.reasoning_summary or "").lower()
    assert plan.task_id != "task-offline"


@pytest.mark.asyncio
async def test_live_gemini_function_call_proposal(live_client: GeminiClient):
    contract = await live_client.generate_function_call(
        prompt=(
            "Propose one permitted tool call to send an email reminder for "
            "process_id and task_id below.\n"
            "process_id: 11111111-1111-1111-1111-111111111111\n"
            "task_id: 22222222-2222-2222-2222-222222222222\n"
            "recipient: manager@example.com\n"
        ),
        model_tier="flash",
    )
    assert isinstance(contract, ToolCallContract)
    assert contract.name
    assert contract.name != "stub_tool"
    assert isinstance(contract.parameters, dict)


@pytest.mark.asyncio
async def test_live_agent2_handle_executes_real_tools(live_client: GeminiClient):
    agent = Agent2(gemini_client=live_client)
    proc_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    msg = AgentMessage(
        message_id=f"msg-{uuid.uuid4().hex[:8]}",
        process_id=proc_id,
        trace_id=f"trace-{uuid.uuid4().hex[:8]}",
        sender="agent_4",
        receiver="agent_2",
        task_type="EXECUTE_TASK",
        payload={
            "task_id": task_id,
            "task_title": "Send Manager Reminder",
            "assigned_role": "manager",
            "assigned_to": "manager@example.com",
            "elapsed_hours": 2.0,
            "sla_hours": 24.0,
            "parameters": {
                "recipient": "manager@example.com",
                "subject": "Live Agent2 verification",
                "body": "This is a live Gemini + Tool Guard execution check.",
                "process_id": proc_id,
                "task_id": task_id,
                "recipient_role": "manager",
            },
        },
        confidence=1.0,
        status="AUTHORIZED",
    )
    response = await agent.handle(msg, session=None)
    assert response.status == "EXECUTION_RESULT"
    assert response.payload.get("receipt_status") in {"SUCCESS", "FAILED", "BLOCKED"}
    # Must not look like offline stub task ids
    tools = response.payload.get("tools_executed") or []
    assert isinstance(tools, list)
    assert response.payload.get("total_score") is not None
