"""Phase 8C: deterministic PO ↔ Invoice matching against persisted records."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.agents.agent2_execution.execution.idempotency import clear_memory_receipts
from app.agents.agent4_orchestrator.workflow_plan.constants import WorkflowStepStatus
from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID
from app.procurement.exceptions import CrossTenantProcurementError
from app.procurement.schemas import CreateInvoiceInput, CreatePurchaseOrderInput, LineItemInput
from app.procurement.seed import (
    VENDOR_BPM_SUPPLIES,
    VENDOR_CODE_IT,
    VENDOR_CODE_TECH,
    VENDOR_TECHSOURCE,
    seed_bpmflow_demo_procurement,
)
from app.procurement.service import get_procurement
from app.tests.test_workflow_step_execution import (
    _complete_predecessors,
    _execute_po,
    _planned_process,
    _po_step,
)
from app.agents.agent2_execution.database.persistence import clear_memory_process_metadata
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

OTHER_TENANT = UUID("00000000-0000-0000-0000-00000000d099")
LAPTOP = LineItemInput(description="Laptop", quantity=Decimal("20"), unit_price=Decimal("75000"))


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


def _po(*, process_id: UUID, tenant_id: UUID = BPMFLOW_DEMO_TENANT_ID, amount: str = "1500000"):
    seed_bpmflow_demo_procurement()
    return get_procurement().create_purchase_order(
        CreatePurchaseOrderInput(
            tenant_id=tenant_id,
            process_id=process_id,
            vendor_ref=VENDOR_CODE_IT,
            currency="LKR",
            amount=Decimal(amount),
            items=[LAPTOP],
        )
    )


def _invoice(
    *,
    process_id: UUID,
    po_id: UUID,
    number: str,
    total: str = "1500000",
    currency: str = "LKR",
    vendor_ref: str = VENDOR_CODE_IT,
    qty: str = "20",
    unit: str = "75000",
    subtotal: str | None = None,
    tenant_id: UUID = BPMFLOW_DEMO_TENANT_ID,
):
    line_total = Decimal(qty) * Decimal(unit)
    return get_procurement().create_invoice(
        CreateInvoiceInput(
            tenant_id=tenant_id,
            process_id=process_id,
            purchase_order_id=po_id,
            vendor_ref=vendor_ref,
            invoice_number=number,
            currency=currency,
            subtotal=Decimal(subtotal) if subtotal is not None else line_total,
            total=Decimal(total),
            items=[
                LineItemInput(
                    description="Laptop",
                    quantity=Decimal(qty),
                    unit_price=Decimal(unit),
                )
            ],
        )
    )


class TestInvoiceMatchingService:
    def test_matched_invoice(self):
        process_id = uuid4()
        po = _po(process_id=process_id)
        invoice = _invoice(process_id=process_id, po_id=po.purchase_order_id, number="INV-MATCH")
        result = get_procurement().match_invoice(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
        )
        assert result.matched is True
        assert result.status == "MATCHED"
        assert result.discrepancy_codes == []
        stored = get_procurement().get_invoice(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
        )
        assert stored is not None
        assert stored.status == "MATCHED"
        assert stored.purchase_order_id == po.purchase_order_id
        assert stored.vendor_id == VENDOR_BPM_SUPPLIES

    def test_amount_mismatch(self):
        process_id = uuid4()
        po = _po(process_id=process_id)
        invoice = _invoice(
            process_id=process_id,
            po_id=po.purchase_order_id,
            number="INV-AMT",
            total="1600000",
            subtotal="1600000",
            qty="20",
            unit="80000",
        )
        result = get_procurement().match_invoice(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
        )
        assert result.matched is False
        assert "AMOUNT_MISMATCH" in result.discrepancy_codes
        assert result.status == "MISMATCH"

    def test_vendor_mismatch(self):
        process_id = uuid4()
        po = _po(process_id=process_id)
        invoice = _invoice(
            process_id=process_id,
            po_id=po.purchase_order_id,
            number="INV-VEN",
            vendor_ref=VENDOR_CODE_TECH,
        )
        result = get_procurement().match_invoice(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
        )
        assert "VENDOR_MISMATCH" in result.discrepancy_codes
        assert result.matched is False
        assert invoice.vendor_id != po.vendor_id or result.vendor_match is False
        assert VENDOR_TECHSOURCE != VENDOR_BPM_SUPPLIES

    def test_currency_mismatch(self):
        process_id = uuid4()
        po = _po(process_id=process_id)
        invoice = _invoice(
            process_id=process_id,
            po_id=po.purchase_order_id,
            number="INV-CCY",
            currency="USD",
        )
        result = get_procurement().match_invoice(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
        )
        assert "CURRENCY_MISMATCH" in result.discrepancy_codes
        assert result.matched is False

    def test_quantity_mismatch(self):
        process_id = uuid4()
        po = _po(process_id=process_id)
        invoice = _invoice(
            process_id=process_id,
            po_id=po.purchase_order_id,
            number="INV-QTY",
            qty="19",
            unit="75000",
            total="1425000",
            subtotal="1425000",
        )
        result = get_procurement().match_invoice(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
        )
        assert "QUANTITY_MISMATCH" in result.discrepancy_codes
        assert result.status != "MATCHED"

    def test_invoice_total_invalid(self):
        process_id = uuid4()
        po = _po(process_id=process_id)
        invoice = _invoice(
            process_id=process_id,
            po_id=po.purchase_order_id,
            number="INV-TOT",
            qty="20",
            unit="70000",
            subtotal="1400000",
            total="1500000",
        )
        result = get_procurement().match_invoice(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
        )
        assert "INVOICE_TOTAL_INVALID" in result.discrepancy_codes
        assert result.matched is False

    def test_cross_tenant_denied(self):
        process_id = uuid4()
        po = _po(process_id=process_id)
        invoice = _invoice(process_id=process_id, po_id=po.purchase_order_id, number="INV-X")
        with pytest.raises(CrossTenantProcurementError):
            get_procurement().match_invoice(tenant_id=OTHER_TENANT, invoice_id=invoice.invoice_id)
        stored = get_procurement().get_invoice(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
        )
        assert stored is not None
        assert stored.status == "RECEIVED"

    def test_idempotent_match(self):
        process_id = uuid4()
        po = _po(process_id=process_id)
        invoice = _invoice(process_id=process_id, po_id=po.purchase_order_id, number="INV-IDEM")
        first = get_procurement().match_invoice(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
        )
        second = get_procurement().match_invoice(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
        )
        assert first.trace_id == second.trace_id
        assert first.status == second.status == "MATCHED"


@pytest.mark.asyncio
class TestInvoiceMatchingWorkflowStep:
    async def test_one_step_one_receipt_no_auto_chain(self, harness, monkeypatch):
        clear_memory_receipts()
        process_id, plan = await _planned_process(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        po_step = _po_step(plan)
        await _execute_po(harness, process_id, plan, po_step)
        po = get_procurement().get_purchase_order_for_process(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        )
        assert po is not None
        invoice = get_procurement().create_invoice(
            CreateInvoiceInput(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                process_id=process_id,
                purchase_order_id=po.purchase_order_id,
                vendor_ref=str(po.vendor_id),
                invoice_number="INV-2026-0098",
                currency=po.currency,
                subtotal=po.subtotal,
                tax=po.tax,
                total=po.total,
                items=[
                    LineItemInput(
                        description=item.description,
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                        purchase_order_item_id=item.item_id,
                    )
                    for item in po.items
                ],
            )
        )
        match_step = next(step for step in plan.steps if step.step_key == "match-invoice")
        other: list[str] = []
        from app.agents.agent2_execution.tools import notification_tools, procurement_tools

        async def forbid(*args, **kwargs):
            other.append("other")
            raise AssertionError("auto-chain")

        monkeypatch.setattr(notification_tools, "send_email", forbid)
        monkeypatch.setattr(procurement_tools, "create_po_draft", forbid)
        from app.agents.agent2_execution.workflow_step.schemas import WorkflowStepExecutionRequest

        result = await harness["executor"].execute_one_step(
            WorkflowStepExecutionRequest(
                process_id=process_id,
                workflow_plan_id=plan.id,
                workflow_step_id=match_step.id,
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        assert result.execution_status == "SUCCESS"
        assert result.tool_name == "match_invoice"
        assert result.implementation_key == "procurement.match_invoice"
        assert result.receipt_id is not None
        assert other == []
        stored = get_procurement().get_invoice(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
        )
        assert stored is not None and stored.status == "MATCHED"
        refreshed = await harness["plans"].get_plan(plan.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert next(s for s in refreshed.steps if s.step_key == "match-invoice").status is WorkflowStepStatus.COMPLETED

    async def test_demo_seed_is_explicit(self):
        from app.procurement.seed import seed_bpmflow_demo_invoices

        numbers = seed_bpmflow_demo_invoices()
        assert numbers["matched"] == "INV-DEMO-MATCHED"
        invoices = get_procurement().list_invoices(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            process_id=UUID("d0d00000-0000-4000-8000-000000000611"),
        )
        assert invoices and invoices[0].invoice_number == "INV-DEMO-MATCHED"
        assert invoices[0].status == "RECEIVED"

    async def test_match_before_po_rejected(self, harness):
        process_id, plan = await _planned_process(harness)
        match_step = next(step for step in plan.steps if step.step_key == "match-invoice")
        from app.agents.agent2_execution.workflow_step.exceptions import (
            DependencyNotCompletedError,
            HumanApprovalRequiredError,
        )
        from app.agents.agent2_execution.workflow_step.schemas import WorkflowStepExecutionRequest

        with pytest.raises((DependencyNotCompletedError, HumanApprovalRequiredError)):
            await harness["executor"].execute_one_step(
                WorkflowStepExecutionRequest(
                    process_id=process_id,
                    workflow_plan_id=plan.id,
                    workflow_step_id=match_step.id,
                ),
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
            )
        assert get_procurement().list_invoices(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        ) == []
