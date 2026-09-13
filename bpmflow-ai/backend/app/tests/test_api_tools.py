"""Tenant-scoped Tool Registry HTTP APIs."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.deps import get_tool_registry_service
from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID
from app.main import app
from app.tests.auth_helpers import override_current_user
from app.tool_registry.constants import ToolActionCode, ToolCategory
from app.tool_registry.repository import InMemoryToolRegistryRepository
from app.tool_registry.seed import seed_bpmflow_tool_registry
from app.tool_registry.service import ToolRegistryService

OTHER_TENANT = uuid4()


@pytest.fixture
def tools_setup():
    repo = InMemoryToolRegistryRepository()
    service = ToolRegistryService(repo)

    async def _override() -> ToolRegistryService:
        return service

    app.dependency_overrides[get_tool_registry_service] = _override
    yield service
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_tools_api_list_and_resolve(tools_setup):
    service = tools_setup
    await seed_bpmflow_tool_registry(service, tenant_id=BPMFLOW_DEMO_TENANT_ID)
    override_current_user(role="requester", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    client = TestClient(app)
    listed = client.get("/api/v1/tools")
    assert listed.status_code == 200
    assert len(listed.json()) == 13
    resolved = client.post(
        "/api/v1/tools/resolve",
        json={
            "action_code": "CREATE_PURCHASE_ORDER",
            "tool_category": "PROCUREMENT",
            "step_type": "SYSTEM_ACTION",
        },
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["tool_name"] == "create_purchase_order"
    assert body["implementation_key"] == "procurement.create_purchase_order"
    assert "smtp" not in str(body).lower()
    assert "password" not in str(body.get("configuration", {})).lower()


@pytest.mark.asyncio
async def test_tools_api_admin_register_and_isolation(tools_setup):
    override_current_user(role="requester", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    client = TestClient(app)
    forbidden = client.post(
        "/api/v1/tools",
        json={
            "tool_name": "create_purchase_order",
            "tool_category": ToolCategory.PROCUREMENT.value,
            "action_code": ToolActionCode.CREATE_PURCHASE_ORDER.value,
            "implementation_key": "procurement.create_purchase_order",
            "input_schema": {"type": "object", "properties": {}},
            "output_schema": {"type": "object", "properties": {}},
        },
    )
    assert forbidden.status_code == 403

    override_current_user(role="admin", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    created = client.post(
        "/api/v1/tools",
        json={
            "tool_name": "create_purchase_order",
            "tool_category": ToolCategory.PROCUREMENT.value,
            "action_code": ToolActionCode.CREATE_PURCHASE_ORDER.value,
            "implementation_key": "procurement.create_purchase_order",
            "allowed_step_types": ["SYSTEM_ACTION"],
            "input_schema": {"type": "object", "properties": {}},
            "output_schema": {"type": "object", "properties": {}},
        },
    )
    assert created.status_code == 201, created.text
    tool_id = created.json()["id"]
    disabled = client.post(f"/api/v1/tools/{tool_id}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    override_current_user(role="admin", tenant_id=OTHER_TENANT)
    hidden = client.get(f"/api/v1/tools/{tool_id}")
    assert hidden.status_code in {403, 404}
