"""Phase 5 DB Tool Registry tests. Resolution only — no tool execution."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.agents.agent2_execution.tools import registry as agent2_registry
from app.agents.agent4_orchestrator.workflow_plan.constants import WorkflowStepType
from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID
from app.core.database import Base
from app.tool_registry.constants import ToolActionCode, ToolCategory
from app.tool_registry.exceptions import (
    ToolAmbiguousError,
    ToolCategoryMismatchError,
    ToolDisabledError,
    ToolNotFoundError,
    ToolNotRegisteredError,
    ToolRegistryError,
    ToolStepTypeNotAllowedError,
)
from app.tool_registry.implementations import REGISTERED_IMPLEMENTATIONS, resolve_implementation
from app.tool_registry.repository import (
    InMemoryToolRegistryRepository,
    SqlAlchemyToolRegistryRepository,
    record_from_input,
)
from app.tool_registry.schemas import RegisterToolInput
from app.tool_registry.seed import bpmflow_demo_tool_specs, seed_bpmflow_tool_registry
from app.tool_registry.service import ToolRegistryService

pytestmark = pytest.mark.asyncio

OTHER_TENANT = UUID("00000000-0000-0000-0000-00000000d099")
OBJECT_SCHEMA = {"type": "object", "properties": {}}


def _po_payload(**overrides) -> RegisterToolInput:
    base = dict(
        tool_name="create_purchase_order",
        display_name="Create purchase order",
        description="PO draft via Agent 2",
        tool_category=ToolCategory.PROCUREMENT,
        action_code=ToolActionCode.CREATE_PURCHASE_ORDER,
        implementation_key="procurement.create_purchase_order",
        allowed_step_types=["SYSTEM_ACTION"],
        input_schema=OBJECT_SCHEMA,
        output_schema=OBJECT_SCHEMA,
    )
    base.update(overrides)
    return RegisterToolInput(**base)


@pytest.fixture
def service() -> ToolRegistryService:
    return ToolRegistryService(InMemoryToolRegistryRepository())


class TestRegisterAndRetrieve:
    async def test_register_and_get_tool(self, service):
        created = await service.register_tool(_po_payload(), tenant_id=BPMFLOW_DEMO_TENANT_ID)
        loaded = await service.get_tool(created.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert loaded.tool_name == "create_purchase_order"
        assert loaded.implementation_key == "procurement.create_purchase_order"
        assert loaded.agent2_tool_name == "create_po_draft"
        assert loaded.enabled is True

    async def test_list_tenant_tools(self, service):
        await service.register_tool(_po_payload(), tenant_id=BPMFLOW_DEMO_TENANT_ID)
        await service.register_tool(
            _po_payload(tool_name="send_email", action_code=ToolActionCode.SEND_EMAIL,
                        tool_category=ToolCategory.COMMUNICATION,
                        implementation_key="communication.send_email",
                        allowed_step_types=["COMMUNICATION"]),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        tools = await service.list_tools(tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert {item.tool_name for item in tools} == {"create_purchase_order", "send_email"}
        assert await service.list_tools(tenant_id=OTHER_TENANT) == []

    async def test_tenant_isolation_get(self, service):
        created = await service.register_tool(_po_payload(), tenant_id=BPMFLOW_DEMO_TENANT_ID)
        with pytest.raises(ToolNotFoundError):
            await service.get_tool(created.id, tenant_id=OTHER_TENANT)


class TestEnableDisable:
    async def test_enable_disable_and_disabled_cannot_resolve(self, service):
        created = await service.register_tool(_po_payload(), tenant_id=BPMFLOW_DEMO_TENANT_ID)
        disabled = await service.disable_tool(created.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert disabled.enabled is False
        with pytest.raises(ToolDisabledError):
            await service.resolve_action(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                action_code="CREATE_PURCHASE_ORDER",
            )
        enabled = await service.enable_tool(created.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert enabled.enabled is True
        resolved = await service.resolve_action(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            action_code="CREATE_PURCHASE_ORDER",
        )
        assert resolved.id == created.id


class TestResolution:
    async def test_resolve_action_to_tool(self, service):
        await service.register_tool(_po_payload(), tenant_id=BPMFLOW_DEMO_TENANT_ID)
        resolved = await service.resolve_action(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            action_code="CREATE_PURCHASE_ORDER",
            tool_category="PROCUREMENT",
            step_type="SYSTEM_ACTION",
        )
        assert resolved.tool_name == "create_purchase_order"

    async def test_category_mismatch(self, service):
        await service.register_tool(_po_payload(), tenant_id=BPMFLOW_DEMO_TENANT_ID)
        with pytest.raises(ToolCategoryMismatchError):
            await service.resolve_action(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                action_code="CREATE_PURCHASE_ORDER",
                tool_category="COMMUNICATION",
            )

    async def test_step_type_mismatch(self, service):
        await service.register_tool(_po_payload(), tenant_id=BPMFLOW_DEMO_TENANT_ID)
        with pytest.raises(ToolStepTypeNotAllowedError):
            await service.resolve_action(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                action_code="CREATE_PURCHASE_ORDER",
                step_type="COMMUNICATION",
            )

    async def test_no_registered_tool(self, service):
        with pytest.raises(ToolNotRegisteredError):
            await service.resolve_action(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                action_code="CREATE_PURCHASE_ORDER",
            )

    async def test_ambiguous_tool(self, service):
        repo = InMemoryToolRegistryRepository()
        svc = ToolRegistryService(repo)
        first = record_from_input(BPMFLOW_DEMO_TENANT_ID, _po_payload())
        second = record_from_input(
            BPMFLOW_DEMO_TENANT_ID,
            _po_payload(tool_name="create_purchase_order_alt", version="2"),
        )
        await repo.insert(first)
        await repo.insert(second)
        with pytest.raises(ToolAmbiguousError):
            await svc.resolve_action(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                action_code="CREATE_PURCHASE_ORDER",
            )

    async def test_tenant_a_cannot_resolve_tenant_b_tool(self, service):
        await service.register_tool(_po_payload(), tenant_id=OTHER_TENANT)
        with pytest.raises(ToolNotRegisteredError):
            await service.resolve_action(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                action_code="CREATE_PURCHASE_ORDER",
            )


class TestAllowListAndSecrets:
    async def test_unknown_implementation_rejected(self, service):
        with pytest.raises(ToolRegistryError) as exc:
            await service.register_tool(
                _po_payload(implementation_key="os.system"),
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
            )
        assert exc.value.error_code == "UNKNOWN_IMPLEMENTATION"

    async def test_no_arbitrary_python_import(self, service):
        with pytest.raises(ToolRegistryError):
            await service.register_tool(
                _po_payload(implementation_key="app.secret.dangerous_handler"),
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
            )
        with pytest.raises(KeyError):
            resolve_implementation("importlib.import_module")

    async def test_secrets_rejected(self, service):
        with pytest.raises(ToolRegistryError) as exc:
            await service.register_tool(
                _po_payload(configuration={"smtp_password": "not-a-real-secret"}),
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
            )
        assert exc.value.error_code == "SECRET_NOT_ALLOWED"

    async def test_input_and_output_schema_validation(self, service):
        with pytest.raises(ToolRegistryError) as exc:
            await service.register_tool(
                _po_payload(input_schema={"hello": "world"}),
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
            )
        assert exc.value.error_code == "INVALID_JSON_SCHEMA"
        created = await service.register_tool(
            _po_payload(
                output_schema={"type": "object", "properties": {"po_number": {"type": "string"}}}
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        assert created.output_schema["properties"]["po_number"]["type"] == "string"


class TestWorkflowStepResolution:
    async def test_workflow_step_resolves_to_tool(self, service):
        await service.register_tool(_po_payload(), tenant_id=BPMFLOW_DEMO_TENANT_ID)
        step = SimpleNamespace(
            required_action="CREATE_PURCHASE_ORDER",
            required_tool_category="PROCUREMENT",
            step_type=WorkflowStepType.SYSTEM_ACTION,
        )
        resolved = await service.resolve_for_step(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, workflow_step=step
        )
        assert resolved.tool_name == "create_purchase_order"
        assert resolved.enabled is True
        assert resolved.tenant_id == BPMFLOW_DEMO_TENANT_ID


class TestAgent2MappingAndSeed:
    async def test_existing_agent2_tools_map_correctly(self, service):
        seeded = await seed_bpmflow_tool_registry(service, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert len(seeded) == 13
        assert len(bpmflow_demo_tool_specs()) == len(REGISTERED_IMPLEMENTATIONS)
        by_key = {item.implementation_key: item for item in seeded}
        for key, agent2_name in REGISTERED_IMPLEMENTATIONS.items():
            assert key in by_key
            assert agent2_registry.contains(agent2_name)
            assert by_key[key].agent2_tool_name == agent2_name

    async def test_seeded_tools_point_to_real_implementations(self, service):
        seeded = await seed_bpmflow_tool_registry(service)
        po = next(item for item in seeded if item.action_code is ToolActionCode.CREATE_PURCHASE_ORDER)
        binding = resolve_implementation(po.implementation_key)
        tool_def = agent2_registry.get(binding.agent2_tool_name)
        assert tool_def is not None
        assert callable(tool_def.handler)

    async def test_procurement_step_resolves_create_purchase_order(self, service):
        await seed_bpmflow_tool_registry(service, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        step = SimpleNamespace(
            required_action="CREATE_PURCHASE_ORDER",
            required_tool_category="PROCUREMENT",
            step_type="SYSTEM_ACTION",
        )
        resolved = await service.resolve_for_step(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, workflow_step=step
        )
        assert resolved.tool_name == "create_purchase_order"
        assert resolved.implementation_key == "procurement.create_purchase_order"
        assert resolved.agent2_tool_name == "create_po_draft"
        assert resolved.enabled is True
        assert resolved.tenant_id == BPMFLOW_DEMO_TENANT_ID
        assert resolved.requires_authorization is True

    async def test_match_invoice_step_resolves_validation_tool(self, service):
        await seed_bpmflow_tool_registry(service, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        step = SimpleNamespace(
            required_action="MATCH_INVOICE",
            required_tool_category="VALIDATION",
            step_type="VALIDATION",
        )
        resolved = await service.resolve_for_step(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, workflow_step=step
        )
        assert resolved.tool_name == "match_invoice"
        assert resolved.implementation_key == "procurement.match_invoice"
        assert resolved.agent2_tool_name == "match_invoice"


class TestSqlAlchemyPersistence:
    async def test_registry_round_trips_through_sqlite(self):
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as session:
            svc = ToolRegistryService(SqlAlchemyToolRegistryRepository(session))
            created = await svc.register_tool(_po_payload(), tenant_id=BPMFLOW_DEMO_TENANT_ID)
            await session.commit()
            tool_id = created.id
        async with factory() as session:
            svc = ToolRegistryService(SqlAlchemyToolRegistryRepository(session))
            loaded = await svc.get_tool(tool_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
            assert loaded.tool_name == "create_purchase_order"
            resolved = await svc.resolve_action(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                action_code="CREATE_PURCHASE_ORDER",
                tool_category="PROCUREMENT",
            )
            assert resolved.id == tool_id
        await engine.dispose()
