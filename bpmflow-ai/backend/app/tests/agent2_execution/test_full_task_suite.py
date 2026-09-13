"""Full task suite is forbidden. Agent 2 executes one WorkflowStep only."""

from __future__ import annotations

import uuid

import pytest

from app.agents.agent2_execution.agent.agent import Agent2
from app.agents.agent2_execution.agent.planner_fallback import FULL_TASK_SUITE_TOOL
from app.agents.agent2_execution.database.persistence import (
    clear_memory_process_metadata,
    get_memory_process_metadata,
)
from app.agents.agent2_execution.execution.idempotency import clear_memory_receipts
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.llm.schemas import AgentMessage


@pytest.fixture(autouse=True)
def _reset_memory_stores():
    clear_memory_receipts()
    clear_memory_process_metadata()
    yield
    clear_memory_receipts()
    clear_memory_process_metadata()


@pytest.mark.asyncio
async def test_full_task_suite_is_forbidden():
    proc_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    message = AgentMessage(
        message_id=f"msg-{uuid.uuid4().hex[:8]}",
        process_id=proc_id,
        trace_id="trace-full-suite",
        sender="agent_4",
        receiver="agent_2",
        task_type="EXECUTE_TASK",
        payload={
            "task_id": task_id,
            "task_title": "Execute procurement workflow",
            "process_type": "procurement",
            "parameters": {
                "tool_name": FULL_TASK_SUITE_TOOL,
                "process_id": proc_id,
                "task_id": task_id,
            },
            "tool_name": FULL_TASK_SUITE_TOOL,
        },
        confidence=1.0,
        status="AUTHORIZED",
    )

    agent = Agent2(gemini_client=GeminiClient(is_offline=True))
    response = await agent.handle(message, session=None)

    assert response.payload["receipt_status"] == "BLOCKED"
    assert (response.payload.get("tools_executed") or []) == []
    assert get_memory_process_metadata(proc_id).get("purchase_order") in (None, {})
