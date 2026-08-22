"""API tests for PROCESS endpoints. No live Supabase database is required."""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.agents.agent4_orchestrator.approval_repository import InMemoryApprovalRepository
from app.agents.agent4_orchestrator.approvals import ApprovalService
from app.agents.agent4_orchestrator.constants import WorkflowStage
from app.agents.agent4_orchestrator.exception_repository import InMemoryExceptionRepository
from app.agents.agent4_orchestrator.exception_service import ExceptionService
from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository
from app.agents.agent4_orchestrator.service import OrchestratorService
from app.agents.agent4_orchestrator.workflow import Agent4Workflow
from app.api.v1.deps import get_agent4_workflow, get_process_repository
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


def _client(
    *,
    role: str = "requester",
    tenant_id: UUID | None = None,
) -> tuple[TestClient, InMemoryProcessRepository]:
    override_current_user(role=role, tenant_id=tenant_id)
    repository = InMemoryProcessRepository()
    orchestrator = OrchestratorService(repository=repository)
    workflow = Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=ApprovalService(
            orchestrator,
            InMemoryApprovalRepository(),
        ),
        exception_service=ExceptionService(
            orchestrator,
            InMemoryExceptionRepository(),
        ),
    )

    async def override_repository() -> InMemoryProcessRepository:
        return repository

    async def override_workflow() -> Agent4Workflow:
        return workflow

    app.dependency_overrides[get_process_repository] = override_repository
    app.dependency_overrides[get_agent4_workflow] = override_workflow
    return TestClient(app), repository


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_health_still_works() -> None:
    client, _ = _client()
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "database" in body
    assert "supabase" in body


def test_create_process() -> None:
    client, _ = _client()
    response = client.post(
        "/api/v1/processes",
        json={
            "name": "Office supplies",
            "process_type": "procurement",
            "description": "Buy stationery",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Office supplies"
    assert body["process_type"] == "procurement"
    assert body["description"] == "Buy stationery"
    assert body["status"] == "draft"
    assert body["current_stage"] == WorkflowStage.DRAFT.value
    assert body["version"] == 1
    assert body["id"]


def test_list_processes() -> None:
    client, _ = _client()
    client.post(
        "/api/v1/processes",
        json={"name": "P1", "process_type": "procurement"},
    )
    client.post(
        "/api/v1/processes",
        json={"name": "P2", "process_type": "approval"},
    )
    response = client.get("/api/v1/processes")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    names = {item["name"] for item in body}
    assert names == {"P1", "P2"}
    for item in body:
        assert item["status"] == "draft"
        assert item["current_stage"] == WorkflowStage.DRAFT.value


def test_get_process() -> None:
    client, _ = _client()
    created = client.post(
        "/api/v1/processes",
        json={"name": "Named", "process_type": "procurement"},
    ).json()
    response = client.get(f"/api/v1/processes/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["name"] == "Named"


def test_get_unknown_process_returns_404() -> None:
    client, _ = _client()
    response = client.get(f"/api/v1/processes/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Process not found"


def test_start_process_moves_draft_to_discovering() -> None:
    client, _ = _client()
    created = client.post(
        "/api/v1/processes",
        json={"name": "Start me", "process_type": "procurement"},
    ).json()
    response = client.post(f"/api/v1/processes/{created['id']}/start")
    assert response.status_code == 200
    body = response.json()
    assert body["process"]["current_stage"] == WorkflowStage.DISCOVERING.value
    assert body["process"]["status"] == "draft"
    assert body["process"]["id"] == created["id"]


def test_start_handles_agent_1_unavailable_without_fake_success() -> None:
    client, _ = _client()
    created = client.post(
        "/api/v1/processes",
        json={"name": "Discovery", "process_type": "procurement"},
    ).json()
    response = client.post(f"/api/v1/processes/{created['id']}/start")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "AGENT_UNAVAILABLE"
    assert body["process"]["current_stage"] == WorkflowStage.DISCOVERING.value
    assert body["process"]["current_stage"] != WorkflowStage.COMPLETED.value
    assert "discovery" not in (body.get("process") or {})
    fetched = client.get(f"/api/v1/processes/{created['id']}").json()
    assert fetched["current_stage"] == WorkflowStage.DISCOVERING.value
    assert fetched["status"] == "draft"


def test_invalid_transition_is_handled() -> None:
    client, _ = _client()
    created = client.post(
        "/api/v1/processes",
        json={"name": "Twice", "process_type": "procurement"},
    ).json()
    first = client.post(f"/api/v1/processes/{created['id']}/start")
    assert first.status_code == 200
    second = client.post(f"/api/v1/processes/{created['id']}/start")
    assert second.status_code == 409
    assert second.json()["detail"] == "Invalid workflow transition"
    fetched = client.get(f"/api/v1/processes/{created['id']}").json()
    assert fetched["current_stage"] == WorkflowStage.DISCOVERING.value


def test_start_unknown_process_returns_404() -> None:
    client, _ = _client()
    response = client.post(f"/api/v1/processes/{uuid4()}/start")
    assert response.status_code == 404
    assert response.json()["detail"] == "Process not found"


def _set_stage(repository: InMemoryProcessRepository, process_id: str, stage: WorkflowStage) -> None:
    asyncio.run(repository.update_process_stage(UUID(process_id), stage))


def _reply(message: AgentMessage, sender: str, message_type: AgentMessageType, payload: dict) -> AgentMessage:
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


def test_plan_resources_advances_to_risk_review() -> None:
    client, repository = _client()
    created = client.post(
        "/api/v1/processes",
        json={"name": "Plan me", "process_type": "procurement"},
    ).json()
    start = client.post(f"/api/v1/processes/{created['id']}/start")
    assert start.status_code == 200

    task_id = uuid4()
    tenant_id = uuid4()
    correlation_id = uuid4()

    async def agent3_reply(message: AgentMessage) -> AgentMessage:
        assert message.metadata.receiver == AGENT_3
        assert message.metadata.task_id == task_id
        assert message.metadata.tenant_id == tenant_id
        assert message.metadata.correlation_id == correlation_id
        return _reply(
            message,
            AGENT_3,
            AgentMessageType.RESOURCE_ALLOCATION_RESPONSE,
            {"status": "PENDING_HUMAN_APPROVAL", "ranked": []},
        )

    with patch(
        "app.agents.agent4_orchestrator.communication_service.AgentCommunicationService.send",
        new_callable=AsyncMock,
        side_effect=agent3_reply,
    ):
        response = client.post(
            f"/api/v1/processes/{created['id']}/plan-resources",
            json={
                "task_id": str(task_id),
                "tenant_id": str(tenant_id),
                "correlation_id": str(correlation_id),
                "human_requirements": {"required_roles": ["approver"]},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["current_stage"] == WorkflowStage.RISK_REVIEW.value
    fetched = client.get(f"/api/v1/processes/{created['id']}").json()
    assert fetched["current_stage"] == WorkflowStage.RISK_REVIEW.value


def test_risk_review_without_findings_reaches_workflow_execution() -> None:
    client, repository = _client()
    created = client.post(
        "/api/v1/processes",
        json={"name": "Risk me", "process_type": "procurement"},
    ).json()
    # Drive the in-memory row to RISK_REVIEW the same way the orchestrator would.
    import asyncio

    process_id = created["id"]
    _set_stage(repository, process_id, WorkflowStage.RISK_REVIEW)

    response = client.post(
        f"/api/v1/processes/{process_id}/risk-review",
        json={},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["human_approval_required"] is False
    assert body["current_stage"] == WorkflowStage.WORKFLOW_EXECUTION.value
    assert body["eligible_for_execution"] is True


def test_risk_review_high_value_opens_approval_gate() -> None:
    client, repository = _client()
    created = client.post(
        "/api/v1/processes",
        json={"name": "Approve me", "process_type": "procurement"},
    ).json()
    _set_stage(repository, created["id"], WorkflowStage.RISK_REVIEW)

    response = client.post(
        f"/api/v1/processes/{created['id']}/risk-review",
        json={"purchase_amount": 25000},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["human_approval_required"] is True
    assert body["current_stage"] == WorkflowStage.AWAITING_HUMAN_APPROVAL.value
    assert body["approval"]["status"] == "PENDING"
    assert body["eligible_for_execution"] is False


def test_execute_dispatches_authorized_agent2_and_advances() -> None:
    client, repository = _client()
    created = client.post(
        "/api/v1/processes",
        json={"name": "Execute me", "process_type": "procurement"},
    ).json()
    _set_stage(repository, created["id"], WorkflowStage.WORKFLOW_EXECUTION)

    async def agent2_reply(message: AgentMessage) -> AgentMessage:
        assert message.status == "AUTHORIZED"
        assert message.metadata.receiver == AGENT_2
        return _reply(
            message,
            AGENT_2,
            AgentMessageType.WORKFLOW_EXECUTION_RESPONSE,
            {"receipt_status": "SUCCESS"},
        )

    with patch(
        "app.agents.agent4_orchestrator.communication_service.AgentCommunicationService.send",
        new_callable=AsyncMock,
        side_effect=agent2_reply,
    ):
        response = client.post(
            f"/api/v1/processes/{created['id']}/execute",
            json={"task_type": "EXECUTE_TASK", "parameters": {"note": "ok"}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["current_stage"] == WorkflowStage.INVOICE_MATCHING.value
    fetched = client.get(f"/api/v1/processes/{created['id']}").json()
    assert fetched["current_stage"] == WorkflowStage.INVOICE_MATCHING.value


def test_complete_invoice_matching_closes_process() -> None:
    client, repository = _client()
    created = client.post(
        "/api/v1/processes",
        json={"name": "Close me", "process_type": "procurement"},
    ).json()
    _set_stage(repository, created["id"], WorkflowStage.INVOICE_MATCHING)

    response = client.post(
        f"/api/v1/processes/{created['id']}/complete-invoice-matching",
        json={"reference": "INV-1001"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["current_stage"] == WorkflowStage.COMPLETED.value
    fetched = client.get(f"/api/v1/processes/{created['id']}").json()
    assert fetched["current_stage"] == WorkflowStage.COMPLETED.value


def test_plan_resources_jwt_tenant_overrides_body() -> None:
    jwt_tenant = uuid4()
    body_tenant = uuid4()
    client, _ = _client(tenant_id=jwt_tenant)
    created = client.post(
        "/api/v1/processes",
        json={"name": "Tenant lock", "process_type": "procurement"},
    ).json()
    assert client.post(f"/api/v1/processes/{created['id']}/start").status_code == 200

    seen: dict = {}

    async def agent3_reply(message: AgentMessage) -> AgentMessage:
        seen["tenant_id"] = message.metadata.tenant_id
        return _reply(
            message,
            AGENT_3,
            AgentMessageType.RESOURCE_ALLOCATION_RESPONSE,
            {"status": "PENDING_HUMAN_APPROVAL"},
        )

    with patch(
        "app.agents.agent4_orchestrator.communication_service.AgentCommunicationService.send",
        new_callable=AsyncMock,
        side_effect=agent3_reply,
    ):
        response = client.post(
            f"/api/v1/processes/{created['id']}/plan-resources",
            json={"task_id": str(uuid4()), "tenant_id": str(body_tenant)},
        )

    assert response.status_code == 200
    assert seen["tenant_id"] == jwt_tenant
    assert seen["tenant_id"] != body_tenant


def test_plan_resources_invalid_stage_is_409() -> None:
    client, _ = _client()
    created = client.post(
        "/api/v1/processes",
        json={"name": "Too early", "process_type": "procurement"},
    ).json()
    response = client.post(
        f"/api/v1/processes/{created['id']}/plan-resources",
        json={"task_id": str(uuid4()), "tenant_id": str(uuid4())},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Invalid workflow transition"
