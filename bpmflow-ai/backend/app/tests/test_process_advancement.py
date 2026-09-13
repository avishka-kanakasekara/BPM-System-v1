"""Phase 6: process advancement engine and POST /processes/{id}/advance."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agents.agent4_orchestrator.advancement_engine import ProcessAdvancementEngine
from app.agents.agent4_orchestrator.advancement_repository import InMemoryAdvancementRepository
from app.agents.agent4_orchestrator.approval_repository import InMemoryApprovalRepository
from app.agents.agent4_orchestrator.approvals import ApprovalService
from app.agents.agent4_orchestrator.constants import WorkflowStage
from app.agents.agent4_orchestrator.exception_repository import InMemoryExceptionRepository
from app.agents.agent4_orchestrator.exception_service import ExceptionService
from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository
from app.agents.agent4_orchestrator.service import OrchestratorService
from app.agents.agent4_orchestrator.workflow import Agent4Workflow
from app.api.v1.deps import (
    get_advancement_repository_dep,
    get_agent4_workflow,
    get_process_advancement_engine,
    get_process_repository,
)
from app.main import app
from app.schemas.agent_message import (
    AGENT_2,
    AGENT_3,
    AGENT_4,
    AgentMessage,
    AgentMessageMetadata,
    AgentMessageType,
)
from app.tests.auth_helpers import override_current_user

DISCOVERY_META = {
    "process_json": {
        "analytics": {
            "risk_facts": {
                "purchase_amount": "25000",
                "currency": "USD",
                "vendor_id": "VENDOR-ACME",
                "cost_centre": "IT-OPS",
                "provided_evidence": ["quotation"],
            }
        }
    }
}


def _reply(message: AgentMessage, sender: str, message_type: AgentMessageType, payload: dict):
    return AgentMessage(
        metadata=AgentMessageMetadata(
            correlation_id=message.metadata.correlation_id,
            process_instance_id=message.metadata.process_instance_id,
            task_id=message.metadata.task_id,
            tenant_id=message.metadata.tenant_id,
            sender=sender,
            receiver=AGENT_4,
            message_type=message_type,
        ),
        payload=payload,
    )


@pytest.fixture
def advance_client():
    override_current_user(role="requester", tenant_id=uuid4())
    process_repo = InMemoryProcessRepository()
    advancement_repo = InMemoryAdvancementRepository()
    orchestrator = OrchestratorService(repository=process_repo)
    workflow = Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=ApprovalService(orchestrator, InMemoryApprovalRepository()),
        exception_service=ExceptionService(orchestrator, InMemoryExceptionRepository()),
    )
    engine = ProcessAdvancementEngine(
        workflow=workflow,
        orchestrator=orchestrator,
        process_repository=process_repo,
        advancement_repository=advancement_repo,
    )

    app.dependency_overrides[get_process_repository] = lambda: process_repo
    app.dependency_overrides[get_agent4_workflow] = lambda: workflow
    app.dependency_overrides[get_advancement_repository_dep] = lambda: advancement_repo
    app.dependency_overrides[get_process_advancement_engine] = lambda: engine

    yield TestClient(app), process_repo, advancement_repo
    app.dependency_overrides.clear()


def _seed_process(repo: InMemoryProcessRepository, *, high_value: bool = True) -> str:
    async def _create():
        row = await repo.insert_process(name="Autopilot", process_type="procurement")
        meta = DISCOVERY_META if high_value else {
            "process_json": {
                "analytics": {
                    "risk_facts": {
                        "purchase_amount": "100",
                        "currency": "USD",
                        "vendor_id": "VENDOR-ACME",
                        "cost_centre": "IT-OPS",
                    }
                }
            }
        }
        repo._records[row.id] = (await repo.get_process(row.id)).model_copy(
            update={"metadata_json": meta}
        )
        return str(row.id)

    return asyncio.run(_create())


def test_advance_from_draft_reaches_human_approval_gate(advance_client) -> None:
    client, _, _ = advance_client
    process_id = _seed_process(advance_client[1])

    async def send_mock(message: AgentMessage) -> AgentMessage:
        if message.metadata.receiver == AGENT_3:
            return _reply(
                message,
                AGENT_3,
                AgentMessageType.RESOURCE_ALLOCATION_RESPONSE,
                {"status": "OK", "ranked": []},
            )
        raise AssertionError(f"Unexpected receiver {message.metadata.receiver}")

    with patch(
        "app.agents.agent4_orchestrator.communication_service.AgentCommunicationService.send",
        new_callable=AsyncMock,
        side_effect=send_mock,
    ):
        response = client.post(
            f"/api/v1/processes/{process_id}/advance",
            json={"idempotency_key": "run-1", "max_steps": 10},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["process"]["current_stage"] == WorkflowStage.AWAITING_HUMAN_APPROVAL.value
    adv = body["advancement"]
    assert adv["status"] == "WAITING_HUMAN"
    assert adv["human_approval_required"] is True
    assert adv["steps_taken"] >= 2
    assert any(a["action"] == "RESOURCE_PLANNING" for a in adv["autonomous_actions"])
    assert any(a["action"] == "RISK_REVIEW" for a in adv["autonomous_actions"])


def test_advance_idempotency_replays_completed_run(advance_client) -> None:
    client, _, advancement_repo = advance_client
    process_id = _seed_process(advance_client[1])

    async def send_mock(message: AgentMessage) -> AgentMessage:
        return _reply(
            message,
            AGENT_3,
            AgentMessageType.RESOURCE_ALLOCATION_RESPONSE,
            {"status": "OK"},
        )

    with patch(
        "app.agents.agent4_orchestrator.communication_service.AgentCommunicationService.send",
        new_callable=AsyncMock,
        side_effect=send_mock,
    ):
        first = client.post(
            f"/api/v1/processes/{process_id}/advance",
            json={"idempotency_key": "idem-42"},
        )
        second = client.post(
            f"/api/v1/processes/{process_id}/advance",
            json={"idempotency_key": "idem-42"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["advancement"]["replayed"] is True


def test_advance_low_risk_reaches_invoice_matching(advance_client) -> None:
    client, repo, _ = advance_client
    process_id = _seed_process(repo, high_value=False)

    async def send_mock(message: AgentMessage) -> AgentMessage:
        if message.metadata.receiver == AGENT_3:
            return _reply(
                message,
                AGENT_3,
                AgentMessageType.RESOURCE_ALLOCATION_RESPONSE,
                {"status": "OK"},
            )
        if message.metadata.receiver == AGENT_2:
            assert message.status == "AUTHORIZED"
            return _reply(
                message,
                AGENT_2,
                AgentMessageType.WORKFLOW_EXECUTION_RESPONSE,
                {"receipt_status": "SUCCESS"},
            )
        raise AssertionError(message.metadata.receiver)

    with patch(
        "app.agents.agent4_orchestrator.communication_service.AgentCommunicationService.send",
        new_callable=AsyncMock,
        side_effect=send_mock,
    ):
        response = client.post(
            f"/api/v1/processes/{process_id}/advance",
            json={"max_steps": 12},
        )

    assert response.status_code == 200
    assert response.json()["process"]["current_stage"] == WorkflowStage.INVOICE_MATCHING.value
    assert response.json()["advancement"]["status"] == "WAITING_INPUT"
