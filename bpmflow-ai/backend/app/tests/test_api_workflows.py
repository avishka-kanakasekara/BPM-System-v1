"""Tenant-scoped WorkflowPlan HTTP APIs."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agents.agent4_orchestrator.workflow_plan.constants import WorkflowStepType
from app.agents.agent4_orchestrator.workflow_plan.repository import InMemoryWorkflowPlanRepository
from app.agents.agent4_orchestrator.workflow_plan.schemas import CreateWorkflowPlanInput
from app.agents.agent4_orchestrator.workflow_plan.service import WorkflowPlanService
from app.api.v1.deps import get_workflow_plan_service
from app.company_directory.repository import InMemoryCompanyDirectoryRepository
from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID, seed_bpmflow_demo_company
from app.company_directory.service import CompanyDirectoryService
from app.main import app
from app.tests.auth_helpers import override_current_user

OTHER_TENANT = uuid4()


@pytest.fixture
def workflow_client():
    directory = CompanyDirectoryService(InMemoryCompanyDirectoryRepository())
    seed_bpmflow_demo_company(directory)
    repo = InMemoryWorkflowPlanRepository()
    service = WorkflowPlanService(repo, directory=directory)

    async def _override() -> WorkflowPlanService:
        return service

    app.dependency_overrides[get_workflow_plan_service] = _override
    override_current_user(role="approver", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    client = TestClient(app)
    yield client, service
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_workflow_api_create_validate_activate(workflow_client):
    client, service = workflow_client
    process_id = uuid4()
    await service._repo.register_process(
        process_id, BPMFLOW_DEMO_TENANT_ID, process_context_schema_version="1.0.0"
    )
    created = client.post("/api/v1/workflows", json={"process_id": str(process_id)})
    assert created.status_code == 201, created.text
    plan_id = created.json()["id"]

    step = client.post(
        f"/api/v1/workflows/{plan_id}/steps",
        json={
            "step_key": "create-po",
            "sequence": 1,
            "name": "Create purchase order",
            "step_type": WorkflowStepType.SYSTEM_ACTION.value,
            "required_action": "CREATE_PURCHASE_ORDER",
            "required_tool_category": "PROCUREMENT",
        },
    )
    assert step.status_code == 201, step.text
    listed = client.get(f"/api/v1/workflows/{plan_id}/steps")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    validated = client.post(f"/api/v1/workflows/{plan_id}/validate")
    assert validated.status_code == 200
    assert validated.json()["valid"] is True

    activated = client.post(f"/api/v1/workflows/{plan_id}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"

    by_process = client.get(f"/api/v1/processes/{process_id}/workflow")
    assert by_process.status_code == 200
    assert by_process.json()["id"] == plan_id


@pytest.mark.asyncio
async def test_workflow_api_hides_other_tenant(workflow_client):
    client, service = workflow_client
    process_id = uuid4()
    await service._repo.register_process(
        process_id, BPMFLOW_DEMO_TENANT_ID, process_context_schema_version="1.0.0"
    )
    plan = await service.create_draft(
        CreateWorkflowPlanInput(process_id=process_id),
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
    )
    override_current_user(role="requester", tenant_id=OTHER_TENANT)
    response = client.get(f"/api/v1/workflows/{plan.id}")
    assert response.status_code in {403, 404}
