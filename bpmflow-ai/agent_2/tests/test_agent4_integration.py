"""
Agent 2 — Agent 4 Inter-Agent Communication Integration Tests

Tests:
1. Inbound scenario 1 (finance approval reminder) via message_handler.process_inbound_message().
2. JWT token validation and error handling for unauthorized / missing tokens.
3. Inbound message authorization status validation.
4. Outbound Agent4Client request header generation.
"""

import uuid
import pytest
from fastapi import HTTPException

from app.agent.agent import Agent2
from app.communication.agent4_client import Agent4Client
from app.communication.message_handler import process_inbound_message
from app.communication.schemas import AgentMessage
from app.llm.gemini_client import GeminiClient
from app.security import auth
from mock_agent4.main import trigger_scenario1_reminder, ScenarioRequest


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
    # Obtain scenario 1 message payload from mock Agent 4
    proc_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    sc_data = trigger_scenario1_reminder(
        ScenarioRequest(process_id=proc_id, task_id=task_id, recipient="henry.taylor@acmeglobal.com")
    )
    raw_msg = sc_data["message"]
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
    sc_data = trigger_scenario1_reminder(ScenarioRequest())
    inbound_msg = AgentMessage.model_validate(sc_data["message"])

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
    sc_data = trigger_scenario1_reminder(ScenarioRequest())
    raw_msg = sc_data["message"]
    raw_msg["status"] = "PENDING"  # Non-AUTHORIZED status

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
# 3. Outbound Agent4Client Unit Test
# ---------------------------------------------------------------------------

def test_agent4_client_headers():
    client = Agent4Client(base_url="http://localhost:8004")
    headers = client._get_headers()
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["Content-Type"] == "application/json"
