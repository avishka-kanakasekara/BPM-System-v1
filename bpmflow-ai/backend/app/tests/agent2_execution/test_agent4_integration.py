"""
Agent 2 — Agent 4 Inter-Agent Communication Integration Tests

The real Agent 4 orchestrator now runs in the same process, so these tests
build authorized wire messages exactly as Agent 4's Agent2Adapter does —
no mock_agent4 module is involved.

Tests:
1. Inbound scenario 1 (finance approval reminder) via message_handler.process_inbound_message().
2. JWT token validation and error handling for unauthorized / missing tokens.
3. Inbound message authorization status validation.
4. Agent 4's Agent2Adapter refuses to forward non-AUTHORIZED messages.
5. Outbound Agent4Client request header generation.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.agents.agent2_execution.agent.agent import Agent2
from app.agents.agent2_execution.communication.agent4_client import Agent4Client
from app.agents.agent2_execution.communication.message_handler import process_inbound_message
from app.agents.agent2_execution.communication.schemas import AgentMessage
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.security import auth


def build_scenario1_reminder(
    process_id: str,
    task_id: str,
    recipient: str = "henry.taylor@acmeglobal.com",
    status: str = "AUTHORIZED",
) -> dict:
    """Authorized finance-approval-reminder message in Agent 2's wire format.

    Mirrors what the real Agent 4 Agent2Adapter produces after the human
    approval gate (status="AUTHORIZED", task_type=EXECUTE_TASK).
    """
    return {
        "message_id": f"msg-sc1-{uuid.uuid4().hex[:6]}",
        "process_id": process_id,
        "trace_id": f"trace-sc1-{uuid.uuid4().hex[:6]}",
        "sender": "agent_4",
        "receiver": "agent_2",
        "task_type": "EXECUTE_TASK",
        "payload": {
            "task_id": task_id,
            "task_title": "Send Finance Approval Reminder",
            "assigned_role": "finance_officer",
            "assigned_to": recipient,
            "elapsed_hours": 18.5,
            "sla_hours": 24.0,
            "parameters": {
                "recipient": recipient,
                "subject": f"Reminder: Finance Approval Pending for Request #{process_id}",
                "body": "Please review pending purchase request finance approval.",
                "process_id": process_id,
                "task_id": task_id,
                "recipient_role": "finance_officer",
            },
        },
        "confidence": 1.0,
        "status": status,
    }


@pytest.fixture
def agent2_instance():
    client = GeminiClient(is_offline=True)
    return Agent2(gemini_client=client)


@pytest.fixture
def valid_jwt_token():
    return auth.create_access_token({"sub": "agent_4", "role": "orchestrator"})


# ---------------------------------------------------------------------------
# 1. Scenario 1 Integration Test (In-process execution)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario1_finance_reminder_inbound(agent2_instance, valid_jwt_token):
    proc_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    raw_msg = build_scenario1_reminder(proc_id, task_id)
    inbound_msg = AgentMessage.model_validate(raw_msg)

    # Process inbound message via message_handler
    response_msg = await process_inbound_message(
        message=inbound_msg,
        auth_token=valid_jwt_token,
        session=None,
        agent_instance=agent2_instance,
    )

    assert isinstance(response_msg, AgentMessage)
    assert response_msg.status == "EXECUTION_RESULT"
    assert response_msg.sender == "agent_2"
    assert response_msg.receiver == "agent_4"

    # Verify execution receipt payload
    payload = response_msg.payload
    assert payload["receipt_status"] in ["DRY_RUN", "SUCCESS"]
    assert "score_breakdown" in payload
    assert payload["total_score"] > 0.0


# ---------------------------------------------------------------------------
# 2. JWT Authentication Error Handling Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inbound_message_invalid_jwt_token(agent2_instance):
    raw_msg = build_scenario1_reminder(str(uuid.uuid4()), str(uuid.uuid4()))
    inbound_msg = AgentMessage.model_validate(raw_msg)

    # Invalid token string should raise 401 Unauthorized
    with pytest.raises(HTTPException) as exc_info:
        await process_inbound_message(
            message=inbound_msg,
            auth_token="invalid.jwt.token.string",
            session=None,
            agent_instance=agent2_instance,
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_inbound_message_unauthorized_status(agent2_instance, valid_jwt_token):
    raw_msg = build_scenario1_reminder(
        str(uuid.uuid4()), str(uuid.uuid4()), status="PENDING"
    )
    inbound_msg = AgentMessage.model_validate(raw_msg)

    with pytest.raises(HTTPException) as exc_info:
        await process_inbound_message(
            message=inbound_msg,
            auth_token=valid_jwt_token,
            session=None,
            agent_instance=agent2_instance,
        )
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# 3. Real Agent 4 adapter: never forwards non-AUTHORIZED work to Agent 2
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent2_adapter_rejects_non_authorized_messages(agent2_instance):
    from app.agents.agent4_orchestrator.adapters import Agent2Adapter
    from app.schemas.agent_message import (
        AGENT_2,
        AGENT_4,
        AgentMessage as SharedAgentMessage,
        AgentMessageMetadata,
        AgentMessageType,
    )

    adapter = Agent2Adapter(agent=agent2_instance)
    message = SharedAgentMessage(
        metadata=AgentMessageMetadata(
            correlation_id=uuid.uuid4(),
            process_instance_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            sender=AGENT_4,
            receiver=AGENT_2,
            message_type=AgentMessageType.WORKFLOW_EXECUTION_REQUEST,
        ),
        payload={"task_type": "EXECUTE_TASK"},
        status=None,  # approval gate never granted AUTHORIZED
    )

    response = await adapter.send(message)

    assert response.metadata.message_type is AgentMessageType.ERROR
    assert response.payload["error"] == "NOT_AUTHORIZED"


# ---------------------------------------------------------------------------
# 4. Outbound Agent4Client Unit Test
# ---------------------------------------------------------------------------

def test_agent4_client_headers():
    client = Agent4Client(base_url="http://localhost:8004")
    headers = client._get_headers()
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["Content-Type"] == "application/json"
