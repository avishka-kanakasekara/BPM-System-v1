"""Phase 8B: tenant-scoped vendors, quotations, and purchase orders."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.agents.agent2_execution.database.persistence import (
    clear_memory_process_metadata,
    get_memory_process_metadata,
)
from app.agents.agent2_execution.execution.idempotency import clear_memory_receipts
from app.agents.agent2_execution.workflow_step.executor import WorkflowStepExecutor
from app.agents.agent3_resources.interfaces import InMemoryResourceRepository
from app.agents.agent3_resources.service import ResourceAllocationService
from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository
from app.agents.agent4_orchestrator.workflow_plan.planner import WorkflowPlanner
from app.agents.agent4_orchestrator.workflow_plan.repository import InMemoryWorkflowPlanRepository
from app.agents.agent4_orchestrator.workflow_plan.service import WorkflowPlanService
from app.company_directory.repository import InMemoryCompanyDirectoryRepository
from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID, seed_bpmflow_demo_company
from app.company_directory.service import CompanyDirectoryService
from app.policy_knowledge import PolicyIngestionService, PolicyRetrievalService
from app.policy_knowledge.repository import InMemoryPolicyRepository
from app.tool_registry.repository import InMemoryToolRegistryRepository
from app.tool_registry.seed import seed_bpmflow_tool_registry
from app.tool_registry.service import ToolRegistryService
from app.tests.test_workflow_planning import _seed_policy
from app.tests.test_workflow_step_execution import (
    _complete_predecessors,
    _execute_po,
    _planned_process,
    _po_step,
)
from app.procurement.exceptions import (
    InsufficientBudgetError,
    MissingQuotationEvidenceError,
    VendorNotFoundError,
)
from app.procurement.schemas import (
    CreatePurchaseOrderInput,
    CreateQuotationInput,
    CreateVendorContactInput,
    CreateVendorInput,
    LineItemInput,
)
from app.procurement.seed import (
    VENDOR_BPM_SUPPLIES,
    VENDOR_CODE_IT,
    seed_bpmflow_demo_procurement,
)
from app.procurement.service import get_procurement
from app.process_context.schemas import QuotationFact
from app.tests.test_workflow_step_execution import (
    _complete_predecessors,
    _execute_po,
    _planned_process,
    _po_step,
)

OTHER_TENANT = UUID("00000000-0000-0000-0000-00000000d099")


@pytest.fixture
async def harness():
    import app.agents.agent2_execution.tools  # noqa: F401

    clear_memory_receipts()
    clear_memory_process_metadata()
    directory = CompanyDirectoryService(InMemoryCompanyDirectoryRepository())
    seed_bpmflow_demo_company(directory)
    seed_bpmflow_demo_procurement(get_procurement())
    processes = InMemoryProcessRepository()
    plans = WorkflowPlanService(InMemoryWorkflowPlanRepository(), directory=directory)
    tools = ToolRegistryService(InMemoryToolRegistryRepository())
    await seed_bpmflow_tool_registry(tools, tenant_id=BPMFLOW_DEMO_TENANT_ID)
    policy_repo = InMemoryPolicyRepository()
    await _seed_policy(PolicyIngestionService(policy_repo), BPMFLOW_DEMO_TENANT_ID)
    planner = WorkflowPlanner(
        plan_service=plans,
        process_repository=processes,
        policy_retrieval=PolicyRetrievalService(policy_repo),
        tool_registry=tools,
        directory=directory,
        allocator=ResourceAllocationService(InMemoryResourceRepository(), directory=directory),
    )
    executor = WorkflowStepExecutor(
        plan_service=plans,
        process_repository=processes,
        tool_registry=tools,
        directory=directory,
        session=None,
    )
    yield {
        "directory": directory,
        "processes": processes,
        "plans": plans,
        "tools": tools,
        "planner": planner,
        "executor": executor,
    }
    clear_memory_receipts()
    clear_memory_process_metadata()


def _seed_vendor(*, tenant_id: UUID, code: str, name: str, vendor_id: UUID | None = None):
    return get_procurement().create_vendor(
        CreateVendorInput(
            tenant_id=tenant_id,
            vendor_id=vendor_id,
            vendor_code=code,
            legal_name=name,
        )
    )


class TestVendorQuotationIsolation:
    def test_vendor_create_and_retrieve(self):
        vendor = _seed_vendor(tenant_id=BPMFLOW_DEMO_TENANT_ID, code="V-A", name="Alpha Ltd")
        found = get_procurement().get_vendor(tenant_id=BPMFLOW_DEMO_TENANT_ID, vendor_id=vendor.vendor_id)
        assert found is not None
        assert found.vendor_code == "V-A"
        assert found.legal_name == "Alpha Ltd"

    def test_vendor_code_unique_per_tenant_not_global(self):
        _seed_vendor(tenant_id=BPMFLOW_DEMO_TENANT_ID, code="VENDOR-001", name="Tenant A vendor")
        other = _seed_vendor(tenant_id=OTHER_TENANT, code="VENDOR-001", name="Tenant B vendor")
        assert other.tenant_id == OTHER_TENANT
        a = get_procurement().repository.get_vendor_by_code(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, vendor_code="VENDOR-001"
        )
        b = get_procurement().repository.get_vendor_by_code(tenant_id=OTHER_TENANT, vendor_code="VENDOR-001")
        assert a is not None and b is not None
        assert a.vendor_id != b.vendor_id

    def test_vendor_tenant_isolation(self):
        vendor = _seed_vendor(tenant_id=BPMFLOW_DEMO_TENANT_ID, code="ISO-1", name="Iso")
        assert get_procurement().get_vendor(tenant_id=OTHER_TENANT, vendor_id=vendor.vendor_id) is None
        assert get_procurement().list_vendors(tenant_id=OTHER_TENANT) == []

    def test_vendor_contact(self):
        vendor = _seed_vendor(tenant_id=BPMFLOW_DEMO_TENANT_ID, code="C-1", name="Contact Co")
        contact = get_procurement().create_vendor_contact(
            CreateVendorContactInput(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                vendor_id=vendor.vendor_id,
                full_name="Ada Vendor",
                email="ada@contact.example.com",
                title="Sales",
            )
        )
        rows = get_procurement().list_vendor_contacts(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, vendor_id=vendor.vendor_id
        )
        assert rows[0].email == "ada@contact.example.com"
        assert contact.vendor_id == vendor.vendor_id

    def test_quotation_create_count_and_vendor(self):
        vendor = _seed_vendor(tenant_id=BPMFLOW_DEMO_TENANT_ID, code="Q-V", name="Quote Vendor")
        process_id = uuid4()
        get_procurement().create_quotation(
            CreateQuotationInput(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                vendor_id=vendor.vendor_id,
                process_id=process_id,
                currency="LKR",
                quotation_number="QT-1",
                total=Decimal("1500000"),
                items=[LineItemInput(description="Laptop", quantity=Decimal("10"), unit_price=Decimal("150000"))],
            )
        )
        get_procurement().create_quotation(
            CreateQuotationInput(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                vendor_id=vendor.vendor_id,
                process_id=process_id,
                currency="LKR",
                quotation_number="QT-2",
                total=Decimal("1480000"),
            )
        )
        assert get_procurement().count_quotations(tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id) == 2
        quotes = get_procurement().list_quotations(tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id)
        assert all(row.vendor_id == vendor.vendor_id for row in quotes)
        assert quotes[0].items[0].line_total == Decimal("1500000.00")

    def test_quotation_tenant_isolation(self):
        vendor = _seed_vendor(tenant_id=BPMFLOW_DEMO_TENANT_ID, code="Q-ISO", name="Iso Quote")
        process_id = uuid4()
        get_procurement().create_quotation(
            CreateQuotationInput(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                vendor_id=vendor.vendor_id,
                process_id=process_id,
                currency="LKR",
                total=Decimal("10"),
            )
        )
        assert get_procurement().count_quotations(tenant_id=OTHER_TENANT, process_id=process_id) == 0

    def test_no_hardcoded_vendor_acme_fallback(self):
        with pytest.raises(VendorNotFoundError) as exc:
            get_procurement().resolve_vendor(tenant_id=BPMFLOW_DEMO_TENANT_ID, vendor_ref="VENDOR-ACME")
        assert exc.value.error_code == "VENDOR_NOT_FOUND"


class TestPurchaseOrderPersistence:
    def test_po_create_relationships_items_and_unique_number(self):
        seed_bpmflow_demo_procurement()
        process_id = uuid4()
        first = get_procurement().create_purchase_order(
            CreatePurchaseOrderInput(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                process_id=process_id,
                vendor_ref=VENDOR_CODE_IT,
                currency="LKR",
                amount=Decimal("1500000"),
                items=[LineItemInput(description="Laptop", quantity=Decimal("10"), unit_price=Decimal("150000"))],
            )
        )
        second = get_procurement().create_purchase_order(
            CreatePurchaseOrderInput(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                process_id=uuid4(),
                vendor_ref=VENDOR_CODE_IT,
                currency="LKR",
                amount=Decimal("100"),
            )
        )
        assert first.po_number != second.po_number
        assert first.process_id == process_id
        assert first.vendor_id == VENDOR_BPM_SUPPLIES
        assert first.items[0].quantity == Decimal("10")
        loaded = get_procurement().get_purchase_order_for_process(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        )
        assert loaded is not None
        assert loaded.purchase_order_id == first.purchase_order_id

    def test_po_tenant_isolation_and_cross_tenant_vendor(self):
        seed_bpmflow_demo_procurement()
        process_id = uuid4()
        po = get_procurement().create_purchase_order(
            CreatePurchaseOrderInput(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                process_id=process_id,
                vendor_ref=VENDOR_CODE_IT,
                currency="LKR",
                amount=Decimal("100"),
            )
        )
        assert get_procurement().get_purchase_order_for_process(
            tenant_id=OTHER_TENANT, process_id=process_id
        ) is None
        with pytest.raises(VendorNotFoundError):
            get_procurement().create_purchase_order(
                CreatePurchaseOrderInput(
                    tenant_id=OTHER_TENANT,
                    process_id=uuid4(),
                    vendor_ref=str(VENDOR_BPM_SUPPLIES),
                    currency="LKR",
                    amount=Decimal("100"),
                )
            )
        assert po.tenant_id == BPMFLOW_DEMO_TENANT_ID

    def test_duplicate_step_returns_same_po(self):
        seed_bpmflow_demo_procurement()
        step_id = uuid4()
        payload = CreatePurchaseOrderInput(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            process_id=uuid4(),
            vendor_ref=VENDOR_CODE_IT,
            currency="LKR",
            amount=Decimal("100"),
            workflow_step_id=step_id,
        )
        first = get_procurement().create_purchase_order(payload)
        second = get_procurement().create_purchase_order(payload)
        assert first.purchase_order_id == second.purchase_order_id
        assert len(get_procurement().repository.list_purchase_orders_for_process(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=first.process_id
        )) == 1

    def test_insufficient_budget_missing_vendor_currency(self):
        seed_bpmflow_demo_procurement()
        with pytest.raises(InsufficientBudgetError):
            get_procurement().create_purchase_order(
                CreatePurchaseOrderInput(
                    tenant_id=BPMFLOW_DEMO_TENANT_ID,
                    process_id=uuid4(),
                    vendor_ref=VENDOR_CODE_IT,
                    currency="LKR",
                    amount=Decimal("2500000"),
                    budget_available=Decimal("1500000"),
                )
            )
        with pytest.raises(VendorNotFoundError):
            get_procurement().create_purchase_order(
                CreatePurchaseOrderInput(
                    tenant_id=BPMFLOW_DEMO_TENANT_ID,
                    process_id=uuid4(),
                    vendor_ref="missing-vendor",
                    currency="LKR",
                    amount=Decimal("100"),
                )
            )
        from app.procurement.exceptions import ProcurementError

        with pytest.raises(ProcurementError) as exc:
            get_procurement().create_purchase_order(
                CreatePurchaseOrderInput(
                    tenant_id=BPMFLOW_DEMO_TENANT_ID,
                    process_id=uuid4(),
                    vendor_ref=VENDOR_CODE_IT,
                    currency="",
                    amount=Decimal("100"),
                )
            )
        assert exc.value.error_code == "MISSING_REQUIRED_EXECUTION_CONTEXT"

    def test_quotation_requirement(self):
        seed_bpmflow_demo_procurement()
        process_id = uuid4()
        with pytest.raises(MissingQuotationEvidenceError):
            get_procurement().create_purchase_order(
                CreatePurchaseOrderInput(
                    tenant_id=BPMFLOW_DEMO_TENANT_ID,
                    process_id=process_id,
                    vendor_ref=VENDOR_CODE_IT,
                    currency="LKR",
                    amount=Decimal("1500000"),
                    min_quotations=2,
                )
            )
        facts = [
            QuotationFact(quotation_id="q-1", vendor="TechSource Lanka", amount=Decimal("1500000"), currency="LKR"),
            QuotationFact(quotation_id="q-2", vendor="BPM Supplies Ltd", amount=Decimal("1480000"), currency="LKR"),
        ]
        po = get_procurement().create_purchase_order(
            CreatePurchaseOrderInput(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                process_id=process_id,
                vendor_ref=VENDOR_CODE_IT,
                currency="LKR",
                amount=Decimal("1500000"),
                min_quotations=2,
                quotation_facts=[fact.model_dump(mode="json") for fact in facts],
            )
        )
        assert get_procurement().count_quotations(tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id) == 2
        assert po.selected_quotation_id is not None

    def test_concurrent_same_step_one_po(self):
        seed_bpmflow_demo_procurement()
        step_id = uuid4()
        process_id = uuid4()

        def _create():
            return get_procurement().create_purchase_order(
                CreatePurchaseOrderInput(
                    tenant_id=BPMFLOW_DEMO_TENANT_ID,
                    process_id=process_id,
                    vendor_ref=VENDOR_CODE_IT,
                    currency="LKR",
                    amount=Decimal("100"),
                    workflow_step_id=step_id,
                )
            )

        first = _create()
        second = _create()
        assert first.purchase_order_id == second.purchase_order_id


@pytest.mark.asyncio
class TestPhase8BWorkflowExecution:
    async def test_pr_2026_0098_creates_real_po(self, harness):
        seed_bpmflow_demo_procurement()
        process_id, plan = await _planned_process(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        po_step = _po_step(plan)
        result = await _execute_po(harness, process_id, plan, po_step)
        assert result.execution_status == "SUCCESS"
        record = get_procurement().get_purchase_order_for_process(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        )
        assert record is not None
        assert record.process_id == process_id
        assert record.vendor_id == VENDOR_BPM_SUPPLIES
        assert record.currency == "LKR"
        assert record.items
        assert get_procurement().count_quotations(tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id) == 2
        meta = get_memory_process_metadata(str(process_id))
        assert meta["purchase_order_ref"]["po_number"] == record.po_number
        assert meta["purchase_order_ref"]["authoritative"] == "purchase_orders"
        assert result.receipt_id is not None
        orders = get_procurement().repository.list_purchase_orders_for_process(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        )
        assert len(orders) == 1

    async def test_pr_2026_0105_no_po(self, harness):
        seed_bpmflow_demo_procurement()
        from app.tests.test_workflow_planning import _ctx, _process_with_context
        from app.company_directory.seed import AUTH_USER_FINANCE_MANAGER

        process_id, _ = await _process_with_context(
            harness,
            _ctx(
                uuid4(),
                amount="2500000",
                budget="1500000",
                quotes=1,
                requester_user=AUTH_USER_FINANCE_MANAGER,
                description="",
            ),
            name="PR-2026-0105",
        )
        result = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        assert any(issue.code == "INSUFFICIENT_BUDGET" for issue in result.issues)
        assert get_procurement().get_purchase_order_for_process(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        ) is None

    async def test_approval_gate_no_po_row(self, harness):
        seed_bpmflow_demo_procurement()
        process_id, plan = await _planned_process(harness)
        po_step = _po_step(plan)
        with pytest.raises(Exception):
            await _execute_po(harness, process_id, plan, po_step)
        assert get_procurement().get_purchase_order_for_process(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        ) is None

    async def test_one_step_registry_and_no_auto_chain(self, harness, monkeypatch):
        seed_bpmflow_demo_procurement()
        process_id, plan = await _planned_process(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        po_step = _po_step(plan)
        other: list[str] = []
        from app.agents.agent2_execution.tools import notification_tools

        async def forbid(*args, **kwargs):
            other.append("email")
            raise AssertionError("auto-chain")

        monkeypatch.setattr(notification_tools, "send_email", forbid)
        result = await _execute_po(harness, process_id, plan, po_step)
        assert result.tool_name == "create_po_draft"
        assert result.implementation_key == "procurement.create_purchase_order"
        assert other == []
        assert "__full_task_suite__" not in str(result.result)

    async def test_conflicting_amount_no_po(self, harness):
        seed_bpmflow_demo_procurement()
        process_id, plan = await _planned_process(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        po_step = _po_step(plan)
        from app.agents.agent2_execution.workflow_step.exceptions import ConflictingExecutionInputError

        with pytest.raises(ConflictingExecutionInputError):
            await _execute_po(
                harness,
                process_id,
                plan,
                po_step,
                caller_parameters={"amount": 1, "vendor_id": "other"},
            )
        assert get_procurement().get_purchase_order_for_process(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        ) is None
