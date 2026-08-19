"""API tests for PROCESS endpoints. No live Supabase database is required."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.agents.agent4_orchestrator.approval_repository import InMemoryApprovalRepository
from app.agents.agent4_orchestrator.approvals import ApprovalService
from app.agents.agent4_orchestrator.constants import WorkflowStage
from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository
from app.agents.agent4_orchestrator.service import OrchestratorService
from app.agents.agent4_orchestrator.workflow import Agent4Workflow
from app.api.v1.deps import get_agent4_workflow, get_process_repository
from app.main import app


def _client() -> tuple[TestClient, InMemoryProcessRepository]:
    repository = InMemoryProcessRepository()
    orchestrator = OrchestratorService(repository=repository)
    workflow = Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=ApprovalService(
            orchestrator,
            InMemoryApprovalRepository(),
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
