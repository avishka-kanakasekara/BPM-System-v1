"""Phase 11: end-to-end procurement lifecycle integration and hardening."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.agents.agent1_discovery.service import run_discovery
from app.agents.agent2_execution.database.persistence import (
    clear_memory_process_metadata,
    get_memory_process_metadata,
)
from app.agents.agent2_execution.execution.idempotency import clear_memory_receipts
from app.agents.agent2_execution.workflow_step.exceptions import (
    HumanApprovalRequiredError,
    PlanNotExecutableError,
)
from app.agents.agent2_execution.workflow_step.executor import WorkflowStepExecutor
from app.agents.agent2_execution.workflow_step.schemas import WorkflowStepExecutionRequest
from app.agents.agent3_resources.interfaces import InMemoryResourceRepository
from app.agents.agent3_resources.service import ResourceAllocationService
from app.agents.agent4_orchestrator import (
    Agent4Workflow,
    ApprovalService,
    ExceptionService,
    InMemoryApprovalRepository,
    InMemoryExceptionRepository,
    OrchestratorService,
    WorkflowStage,
)
from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository
from app.agents.agent4_orchestrator.state_machine import TransitionContext
from app.agents.agent4_orchestrator.workflow_plan.constants import WorkflowPlanStatus
from app.agents.agent4_orchestrator.workflow_plan.planner import WorkflowPlanner
from app.agents.agent4_orchestrator.workflow_plan.repository import InMemoryWorkflowPlanRepository
from app.agents.agent4_orchestrator.workflow_plan.service import WorkflowPlanService
from app.company_directory.repository import InMemoryCompanyDirectoryRepository
from app.company_directory.seed import (
    AUTH_USER_FINANCE_MANAGER,
    AUTH_USER_REQUESTER,
    BPMFLOW_DEMO_TENANT_ID,
    seed_bpmflow_demo_company,
)
from app.company_directory.service import CompanyDirectoryService
from app.core.config import Settings
from app.main import app
from app.models.process import Process
from app.monitoring.recommendations import TobeRecommendationService
from app.monitoring.recorder import record_exception, record_process_snapshot
from app.monitoring.service import MonitoringService
from app.policy_knowledge import PolicyIngestionService, PolicyRetrievalService
from app.policy_knowledge.repository import InMemoryPolicyRepository
from app.procurement.schemas import CreateInvoiceInput, LineItemInput
from app.procurement.seed import VENDOR_TECHSOURCE, seed_bpmflow_demo_procurement
from app.procurement.service import get_procurement
from app.process_context.schemas import ProcessContext
from app.tests.auth_helpers import override_current_user
from app.tests.test_phase9_document_intelligence import (
    FakeUpload,
    HIGH_VALUE_TEXT,
    VIOLATION_TEXT,
    _pdf_with_text,
    _session,
)
from app.tests.test_workflow_planning import _seed_policy
from app.tests.test_workflow_step_execution import _complete_predecessors, _execute_po, _po_step
from app.tool_registry.repository import InMemoryToolRegistryRepository
from app.tool_registry.seed import seed_bpmflow_tool_registry
from app.tool_registry.service import ToolRegistryService

OTHER_TENANT = UUID("00000000-0000-0000-0000-00000000d099")
MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "supabase" / "migrations"
EXPECTED_MIGRATIONS = [
    "0001_init.sql",
    "0002_agent1_discovery.sql",
    "0003_agent4_workflow.sql",
    "0004_agent3_resource_persistence.sql",
    "0005_agent3_synthetic_seed.sql",
    "0006_agent3_write_path_persistence.sql",
    "0007_agent2_execution.sql",
    "0008_company_policy_knowledge.sql",
    "0009_admin_role_provisioning_notes.sql",
    "0010_agent2_scheduled_jobs.sql",
    "0011_agent2_scheduler_claiming.sql",
    "0012_schema_hardening.sql",
    "0013_policy_pgvector.sql",
    "0014_process_advancement.sql",
    "0015_process_context.sql",
    "0016_company_directory.sql",
    "0017_workflow_plan.sql",
    "0018_tool_registry.sql",
    "0019_procurement.sql",
    "0020_invoices.sql",
    "0021_process_exceptions.sql",
    "0022_discovery_document_index.sql",
    "0023_tobe_recommendations.sql",
    "0024_phase12_rls_hardening.sql",
]


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
    orchestrator = OrchestratorService(repository=processes)
    exceptions = InMemoryExceptionRepository()
    workflow = Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=ApprovalService(orchestrator, InMemoryApprovalRepository()),
        exception_service=ExceptionService(orchestrator, exceptions),
    )
    yield {
        "directory": directory,
        "processes": processes,
        "plans": plans,
        "tools": tools,
        "planner": planner,
        "executor": executor,
        "orchestrator": orchestrator,
        "workflow": workflow,
        "exceptions": exceptions,
        "policy_repo": policy_repo,
    }
    clear_memory_receipts()
    clear_memory_process_metadata()


def _discover(text: str, *, tenant_id: UUID = BPMFLOW_DEMO_TENANT_ID, name: str = "pr.pdf"):
    db = _session()
    message = run_discovery(
        [FakeUpload(name, _pdf_with_text(text), "application/pdf")],
        db,
        tenant_id=tenant_id,
        requester_user_id=AUTH_USER_REQUESTER,
    )
    row = db.get(Process, message.process_id)
    ctx = ProcessContext.model_validate(row.process_context)
    return message, row, ctx


async def _adopt_discovery(harness, *, name: str, ctx: ProcessContext, created_by: UUID):
    record = await harness["processes"].insert_process(
        name=name,
        process_type="procurement",
        description=ctx.purchase.description,
        created_by=created_by,
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
    )
    adopted = ctx.model_copy(update={"process_id": record.id, "tenant_id": BPMFLOW_DEMO_TENANT_ID})
    harness["processes"]._records[record.id] = record.model_copy(
        update={"process_context": adopted.model_dump(mode="json")}
    )
    return record.id, adopted


async def _happy_path_to_completion(harness):
    seed_bpmflow_demo_procurement()
    _message, _row, ctx = _discover(HIGH_VALUE_TEXT, name="Purchase_Request_Test_High_Value.pdf")
    assert ctx.purchase.amount == Decimal("1500000")
    assert ctx.purchase.purchase_request_id == "PR-2026-0098"
    assert ctx.evidence
    process_id, ctx = await _adopt_discovery(
        harness, name="PR-2026-0098", ctx=ctx, created_by=AUTH_USER_REQUESTER
    )
    planned = await harness["planner"].generate_plan(
        process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
    )
    assert planned.status == WorkflowPlanStatus.READY.value
    keys = [step.step_key for step in planned.steps]
    assert "finance-approval" in keys
    assert "senior-management-approval" in keys
    assert "create-purchase-order" in keys
    assert "match-invoice" in keys
    for step in planned.steps:
        if step.approval_required:
            assert step.responsible_employee_id is not None
            assert step.status.value == "WAITING_HUMAN_APPROVAL"
    activated = await harness["plans"].activate(
        planned.workflow_plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
    )
    assert activated.status is WorkflowPlanStatus.ACTIVE
    await harness["processes"].update_process_stage(process_id, WorkflowStage.WORKFLOW_EXECUTION)
    record_process_snapshot(
        process_id=process_id,
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
        name="PR-2026-0098",
        current_stage=WorkflowStage.WORKFLOW_EXECUTION.value,
        status="ACTIVE",
        workflow_plan_id=activated.id,
        purchase_request_id="PR-2026-0098",
        event_type="discovery_completed",
        actor="agent1_discovery",
    )
    po_step = _po_step(activated)
    with pytest.raises(HumanApprovalRequiredError):
        await _execute_po(harness, process_id, activated, po_step)
    assert get_procurement().get_purchase_order_for_process(
        tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
    ) is None
    plan = await _complete_predecessors(harness, activated, through_approvals=True)
    po_result = await _execute_po(harness, process_id, plan, _po_step(plan))
    assert po_result.execution_status == "SUCCESS"
    assert po_result.tool_name == "create_po_draft"
    po = get_procurement().get_purchase_order_for_process(
        tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
    )
    assert po is not None
    assert po.process_id == process_id
    invoice = get_procurement().create_invoice(
        CreateInvoiceInput(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            process_id=process_id,
            purchase_order_id=po.purchase_order_id,
            vendor_ref=str(po.vendor_id),
            invoice_number="INV-PR-2026-0098",
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
    match_result = await harness["executor"].execute_one_step(
        WorkflowStepExecutionRequest(
            process_id=process_id,
            workflow_plan_id=plan.id,
            workflow_step_id=match_step.id,
        ),
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
    )
    assert match_result.execution_status == "SUCCESS"
    assert match_result.tool_name == "match_invoice"
    stored_invoice = get_procurement().get_invoice(
        tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
    )
    assert stored_invoice is not None and stored_invoice.status == "MATCHED"
    await harness["orchestrator"].move_process(
        process_id,
        WorkflowStage.INVOICE_MATCHING,
        reason="invoice matching",
        transition_context=TransitionContext(execution_receipt_status="SUCCESS"),
    )
    completion = await harness["workflow"].complete_invoice_matching(
        process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_number="INV-PR-2026-0098"
    )
    assert completion.success is True
    assert completion.current_stage is WorkflowStage.COMPLETED
    stored = harness["processes"]._records[process_id]
    record_process_snapshot(
        process_id=process_id,
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
        name="PR-2026-0098",
        current_stage=WorkflowStage.COMPLETED.value,
        status="COMPLETED",
        created_at=stored.created_at,
        completed_at=stored.updated_at,
        workflow_plan_id=plan.id,
        purchase_request_id="PR-2026-0098",
        event_type="process_completed",
        actor="agent4_orchestrator",
    )
    return process_id, plan, po, invoice, ctx


@pytest.mark.asyncio
class TestPhase11HappyPath:
    async def test_pr_2026_0098_full_lifecycle(self, harness):
        process_id, plan, po, invoice, ctx = await _happy_path_to_completion(harness)
        assert ctx.purchase.amount_source == "extracted_evidence"
        amount_evidence = [item for item in ctx.evidence if item.field == "amount"]
        assert amount_evidence
        loaded = ProcessContext.model_validate(
            (await harness["processes"].get_process(process_id)).process_context
        )
        assert loaded.purchase.amount == Decimal("1500000")
        assert loaded.budget.available_amount == Decimal("2000000")
        active = await harness["plans"].get_active_plan(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        )
        assert active is not None and active.id == plan.id
        meta = get_memory_process_metadata(str(process_id)).get("purchase_order_ref")
        assert meta["id"] == str(po.purchase_order_id)
        assert invoice.process_id == po.process_id == process_id
        assert await harness["orchestrator"].get_current_stage(process_id) is WorkflowStage.COMPLETED
        monitoring = MonitoringService().report(BPMFLOW_DEMO_TENANT_ID, process_id)
        types = {event.event_type for event in monitoring.timeline}
        assert "workflow_step_started" in types
        assert "process_completed" in types
        assert monitoring.kpis.completed_processes == 1
        recs = await TobeRecommendationService().generate(BPMFLOW_DEMO_TENANT_ID, process_id)
        assert recs
        assert all(item.evidence for item in recs)
        assert all(item.activates_workflow is False for item in recs)
        again = await TobeRecommendationService().generate(BPMFLOW_DEMO_TENANT_ID, process_id)
        assert {item.id for item in recs} == {item.id for item in again}
        _ = VENDOR_TECHSOURCE


@pytest.mark.asyncio
class TestPhase11InvalidPath:
    async def test_pr_2026_0105_blocked_no_po_no_completion(self, harness):
        _message, _row, ctx = _discover(VIOLATION_TEXT, name="Purchase_Request_Policy_Violation_Test.pdf")
        assert ctx.purchase.amount == Decimal("2500000")
        assert ctx.budget.available_amount == Decimal("1500000")
        ctx = ctx.model_copy(
            update={
                "requester": ctx.requester.model_copy(
                    update={"user_id": AUTH_USER_FINANCE_MANAGER, "identity_mapped": True}
                )
            }
        )
        process_id, ctx = await _adopt_discovery(
            harness, name="PR-2026-0105", ctx=ctx, created_by=AUTH_USER_FINANCE_MANAGER
        )
        planned = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        codes = {issue.code for issue in planned.issues}
        assert "INSUFFICIENT_BUDGET" in codes
        assert planned.execution_ready is False
        with pytest.raises(Exception):
            await harness["plans"].activate(planned.workflow_plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        await harness["processes"].update_process_stage(process_id, WorkflowStage.WORKFLOW_EXECUTION)
        result = await harness["workflow"].capture_failure(
            process_id,
            "PR-2026-0105 budget, quotation, and SoD violations",
            exception_code="BUDGET_EXCEEDED",
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            details={"purchase_request_id": "PR-2026-0105", "codes": sorted(codes)},
        )
        assert result.current_stage is WorkflowStage.EXCEPTION
        assert get_procurement().get_purchase_order_for_process(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        ) is None
        blocked = await harness["workflow"].complete_invoice_matching(
            process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        assert blocked.success is False
        record_process_snapshot(
            process_id=process_id,
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            name="PR-2026-0105",
            current_stage="EXCEPTION",
            status="EXCEPTION",
            purchase_request_id="PR-2026-0105",
            event_type="risk_review",
            actor="agent4_orchestrator",
        )
        record_exception(
            process_id=process_id,
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            exception_id=result.bpm_exception.id,
            code="BUDGET_EXCEEDED",
            status="open",
        )
        analytics = MonitoringService().exception_analytics(BPMFLOW_DEMO_TENANT_ID, process_id)
        assert "BUDGET_EXCEEDED" in analytics.exceptions_by_code


@pytest.mark.asyncio
class TestPhase11Boundaries:
    async def _plan_only(self, harness):
        from app.tests.test_workflow_step_execution import _planned_process

        return await _planned_process(harness)

    async def test_four_agent_responsibility_split(self, harness):
        from app.agents.agent1_discovery import service as agent1
        from app.agents.agent2_execution.workflow_step.executor import WorkflowStepExecutor as Ex
        from app.agents.agent3_resources.service import ResourceAllocationService as Alloc
        from app.agents.agent4_orchestrator.workflow import Agent4Workflow as Wf

        assert hasattr(agent1, "run_discovery")
        assert not hasattr(agent1, "execute_one_step")
        assert not hasattr(Alloc, "execute_one_step")
        assert hasattr(Ex, "execute_one_step")
        assert not hasattr(Ex, "move_process")
        assert hasattr(Wf, "complete_invoice_matching")
        assert not hasattr(Wf, "create_po_draft")
        process_id, plan = await self._plan_only(harness)
        with pytest.raises(HumanApprovalRequiredError):
            await _execute_po(harness, process_id, plan, _po_step(plan))

    async def test_one_step_no_auto_chain(self, harness, monkeypatch):
        process_id, plan = await self._plan_only(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        other: list[str] = []
        from app.agents.agent2_execution.tools import notification_tools

        async def forbid(*args, **kwargs):
            other.append("chained")
            raise AssertionError("auto-chain")

        monkeypatch.setattr(notification_tools, "send_email", forbid)
        result = await _execute_po(harness, process_id, plan, _po_step(plan))
        assert result.execution_status == "SUCCESS"
        assert other == []
        assert get_procurement().list_invoices(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        ) == []

    async def test_superseded_and_duplicate_po(self, harness):
        process_id, plan = await self._plan_only(harness)
        second = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        assert second.version == 2
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        await _execute_po(harness, process_id, plan, _po_step(plan))
        replay = await _execute_po(harness, process_id, plan, _po_step(plan))
        assert replay.duplicate is True
        pos = get_procurement().repository.list_purchase_orders_for_process(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        )
        assert len(pos) == 1
        with pytest.raises(PlanNotExecutableError):
            await harness["executor"].execute_one_step(
                WorkflowStepExecutionRequest(
                    process_id=process_id,
                    workflow_plan_id=second.workflow_plan_id,
                    workflow_step_id=second.steps[0].id,
                ),
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
            )

    async def test_concurrent_step_execution(self, harness):
        process_id, plan = await self._plan_only(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        step = _po_step(plan)

        async def _run():
            return await _execute_po(harness, process_id, plan, step)

        results = await asyncio.gather(_run(), _run(), return_exceptions=True)
        successes = [item for item in results if not isinstance(item, Exception)]
        assert successes
        pos = get_procurement().repository.list_purchase_orders_for_process(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        )
        assert len(pos) == 1

    async def test_tenant_isolation_e2e(self, harness):
        _process_id, plan = await self._plan_only(harness)
        with pytest.raises(Exception):
            await harness["plans"].get_plan(plan.id, tenant_id=OTHER_TENANT)
        override_current_user(role="requester", tenant_id=OTHER_TENANT)
        client = TestClient(app)
        denied = client.get(f"/api/v1/processes/{plan.process_id}/monitoring")
        assert denied.status_code in {403, 404}
        app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestPhase11ErrorPaths:
    async def test_unparseable_document(self):
        db = _session()
        message = run_discovery(
            [FakeUpload("broken.pdf", b"not-a-pdf", "application/pdf")],
            db,
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        assert message is not None

    async def test_missing_invoice_does_not_complete(self, harness):
        from app.tests.test_workflow_step_execution import _planned_process

        process_id, plan = await _planned_process(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        await _execute_po(harness, process_id, plan, _po_step(plan))
        await harness["orchestrator"].move_process(
            process_id,
            WorkflowStage.INVOICE_MATCHING,
            reason="ready to match",
            transition_context=TransitionContext(execution_receipt_status="SUCCESS"),
        )
        result = await harness["workflow"].complete_invoice_matching(
            process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        assert result.success is False
        assert await harness["orchestrator"].get_current_stage(process_id) is not WorkflowStage.COMPLETED


def test_migrations_ordered():
    names = sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))
    assert names == EXPECTED_MIGRATIONS
    prefixes = [name.split("_", 1)[0] for name in names]
    assert prefixes == sorted(prefixes)


def test_production_config_rejects_insecure_defaults():
    insecure = Settings(
        ENV="production",
        MOCK_LLM=True,
        DEBUG=False,
        GEMINI_API_KEY="real-key",
        EMAIL_DRY_RUN=False,
    )
    with pytest.raises(RuntimeError, match="MOCK_LLM"):
        insecure.assert_production_config()
    Settings(ENV="development", MOCK_LLM=True).assert_production_config()


def test_demo_seed_is_explicit_and_blocked_in_production(monkeypatch):
    override_current_user(role="admin", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    client = TestClient(app)

    class ProdSettings:
        ENV = "production"
        DEBUG = False

    monkeypatch.setattr("app.api.v1.routes_procurement.settings", ProdSettings())
    blocked = client.post("/api/v1/vendors/seed-demo")
    assert blocked.status_code == 403

    class DevSettings:
        ENV = "development"
        DEBUG = True

    monkeypatch.setattr("app.api.v1.routes_procurement.settings", DevSettings())
    allowed = client.post("/api/v1/vendors/seed-demo")
    assert allowed.status_code == 201
    app.dependency_overrides.clear()


def test_frontend_process_contract_fields_remain():
    from app.schemas.process import ProcessResponse

    required = {"id", "name", "process_type", "status", "current_stage", "version", "created_at", "updated_at"}
    assert required.issubset(set(ProcessResponse.model_fields))
    frontend = (Path(__file__).resolve().parents[3] / "frontend" / "src" / "types" / "api.ts").read_text(
        encoding="utf-8"
    )
    for stage in (
        "DRAFT",
        "DISCOVERING",
        "RESOURCE_PLANNING",
        "RISK_REVIEW",
        "AWAITING_HUMAN_APPROVAL",
        "WORKFLOW_EXECUTION",
        "INVOICE_MATCHING",
        "EXCEPTION",
        "COMPLETED",
    ):
        assert stage in frontend


def test_api_smoke_authenticated_paths():
    from app.monitoring.demo import PROCESS_0098, seed_procurement_demo

    seed_procurement_demo()
    override_current_user(role="approver", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code in {200, 503}
    assert client.get(f"/api/v1/processes/{PROCESS_0098}/monitoring").status_code == 200
    assert client.get(f"/api/v1/processes/{PROCESS_0098}/kpis").status_code == 200
    assert client.get(f"/api/v1/processes/{PROCESS_0098}/timeline").status_code == 200
    assert client.post(f"/api/v1/processes/{PROCESS_0098}/recommendations/generate").status_code == 200
    assert client.get("/api/v1/exceptions").status_code == 200
    override_current_user(role="requester", tenant_id=OTHER_TENANT)
    assert client.get(f"/api/v1/processes/{PROCESS_0098}/kpis").status_code == 404
    app.dependency_overrides.clear()
