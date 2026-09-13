"""Phase 7: Agent 2 executes exactly one authorized WorkflowStep."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.agents.agent2_execution.agent.agent import Agent2
from app.agents.agent2_execution.agent.planner_fallback import FULL_TASK_SUITE_TOOL
from app.agents.agent2_execution.database.persistence import (
    clear_memory_process_metadata,
    get_memory_process_metadata,
)
from app.agents.agent2_execution.execution.idempotency import clear_memory_receipts
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.llm.schemas import AgentMessage
from app.agents.agent2_execution.workflow_step.exceptions import (
    ConflictingExecutionInputError,
    CrossTenantDeniedError,
    DependencyNotCompletedError,
    HumanApprovalRequiredError,
    PlanNotExecutableError,
    WorkflowStepExecutionError,
)
from app.agents.agent2_execution.workflow_step.executor import WorkflowStepExecutor
from app.agents.agent2_execution.workflow_step.schemas import WorkflowStepExecutionRequest
from app.agents.agent3_resources.interfaces import InMemoryResourceRepository
from app.agents.agent3_resources.service import ResourceAllocationService
from app.agents.agent4_orchestrator.constants import WorkflowStage
from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository
from app.agents.agent4_orchestrator.workflow_plan.constants import WorkflowPlanStatus, WorkflowStepStatus
from app.agents.agent4_orchestrator.workflow_plan.planner import WorkflowPlanner
from app.agents.agent4_orchestrator.workflow_plan.repository import InMemoryWorkflowPlanRepository
from app.agents.agent4_orchestrator.workflow_plan.service import WorkflowPlanService
from app.company_directory.repository import InMemoryCompanyDirectoryRepository
from app.company_directory.seed import (
    AUTH_USER_REQUESTER,
    BPMFLOW_DEMO_TENANT_ID,
    seed_bpmflow_demo_company,
)
from app.company_directory.service import CompanyDirectoryService
from app.policy_knowledge import (
    PolicyCategory,
    PolicyCreateRequest,
    PolicyIngestionService,
    PolicyRetrievalService,
    PolicyRule,
    PolicyRuleType,
)
from app.policy_knowledge.constants import PolicyOperator
from app.policy_knowledge.repository import InMemoryPolicyRepository
from app.procurement.service import get_procurement
from app.process_context.schemas import (
    BudgetFacts,
    EvidenceItem,
    ProcessContext,
    PurchaseFacts,
    QuotationFact,
    RequesterIdentity,
)
from app.tool_registry.repository import InMemoryToolRegistryRepository
from app.tool_registry.seed import seed_bpmflow_tool_registry
from app.tool_registry.service import ToolRegistryService
from app.tests.test_workflow_planning import _seed_policy

pytestmark = pytest.mark.asyncio

OTHER_TENANT = UUID("00000000-0000-0000-0000-00000000d099")


def _ctx(process_id: UUID) -> ProcessContext:
    return ProcessContext(
        process_id=process_id,
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
        requester=RequesterIdentity(user_id=AUTH_USER_REQUESTER, identity_mapped=True),
        purchase=PurchaseFacts(
            description="PR-2026-0098 laptop refresh",
            amount=Decimal("1500000"),
            currency="LKR",
            vendor_id="vendor-it-01",
            purchase_request_id="PR-2026-0098",
            amount_source="extracted_evidence",
        ),
        budget=BudgetFacts(
            available_amount=Decimal("2000000"),
            currency="LKR",
            source="company_repository",
        ),
        quotations=[
            QuotationFact(
                quotation_id="q-1",
                vendor="Vendor 1",
                amount=Decimal("1500000"),
                currency="LKR",
                evidence_id="quotation-1",
            ),
            QuotationFact(
                quotation_id="q-2",
                vendor="Vendor 2",
                amount=Decimal("1500000"),
                currency="LKR",
                evidence_id="quotation-2",
            ),
        ],
        evidence=[EvidenceItem(evidence_id="purchase-request", type="purchase_request")],
    )


@pytest.fixture
async def harness():
    import app.agents.agent2_execution.tools  # noqa: F401

    clear_memory_receipts()
    clear_memory_process_metadata()
    directory = CompanyDirectoryService(InMemoryCompanyDirectoryRepository())
    seed_bpmflow_demo_company(directory)
    from app.procurement.seed import seed_bpmflow_demo_procurement
    from app.procurement.service import get_procurement

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


async def _planned_process(harness):
    record = await harness["processes"].insert_process(
        name="PR-2026-0098",
        process_type="procurement",
        description="PR-2026-0098 laptop refresh",
        created_by=AUTH_USER_REQUESTER,
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
    )
    ctx = _ctx(record.id)
    harness["processes"]._records[record.id] = record.model_copy(
        update={"process_context": ctx.model_dump(mode="json")}
    )
    result = await harness["planner"].generate_plan(
        process_id=record.id, tenant_id=BPMFLOW_DEMO_TENANT_ID
    )
    activated = await harness["plans"].activate(
        result.workflow_plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
    )
    await harness["processes"].update_process_stage(record.id, WorkflowStage.WORKFLOW_EXECUTION)
    return record.id, activated


async def _complete_predecessors(harness, plan, *, through_approvals: bool):
    for step in plan.steps:
        if step.step_key == "create-purchase-order":
            continue
        if step.step_key == "match-invoice":
            continue
        if step.step_key.endswith("-approval") and not through_approvals:
            continue
        await harness["plans"].complete_human_step(
            plan.id, step.id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
    return await harness["plans"].get_plan(plan.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)


def _po_step(plan):
    return next(step for step in plan.steps if step.step_key == "create-purchase-order")


async def _execute_po(harness, process_id, plan, step, **kwargs):
    return await harness["executor"].execute_one_step(
        WorkflowStepExecutionRequest(
            process_id=process_id,
            workflow_plan_id=plan.id,
            workflow_step_id=step.id,
            process_context_ref=process_id,
            **kwargs,
        ),
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
    )


class TestOneStepWorkflowExecution:
    async def test_draft_plan_rejected(self, harness):
        process_id, plan = await _planned_process(harness)
        await harness["plans"]._repo.update_plan_status(
            plan.id, WorkflowPlanStatus.DRAFT, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        po = _po_step(plan)
        with pytest.raises(PlanNotExecutableError) as exc:
            await _execute_po(harness, process_id, plan, po)
        assert exc.value.error_code == "PLAN_NOT_EXECUTABLE"

    async def test_waiting_human_approval_rejected(self, harness):
        process_id, plan = await _planned_process(harness)
        finance = next(step for step in plan.steps if step.step_key == "finance-approval")
        with pytest.raises(HumanApprovalRequiredError):
            await harness["executor"].execute_one_step(
                WorkflowStepExecutionRequest(
                    process_id=process_id,
                    workflow_plan_id=plan.id,
                    workflow_step_id=finance.id,
                ),
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
            )
        assert get_memory_process_metadata(str(process_id)).get("purchase_order") is None

    async def test_po_before_approvals_rejected(self, harness):
        process_id, plan = await _planned_process(harness)
        po = _po_step(plan)
        with pytest.raises((DependencyNotCompletedError, HumanApprovalRequiredError)):
            await _execute_po(harness, process_id, plan, po)
        assert "purchase_order" not in get_memory_process_metadata(str(process_id))

    async def test_high_value_po_after_approvals_one_step(self, harness, monkeypatch):
        process_id, plan = await _planned_process(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        po = _po_step(plan)
        calls: list[str] = []
        other_tools: list[str] = []

        from app.agents.agent2_execution.tools import procurement_tools, notification_tools

        original = procurement_tools.create_po_draft

        async def spy(session, data):
            calls.append("po")
            return await original(session, data)

        async def forbid(*args, **kwargs):
            other_tools.append("other")
            raise AssertionError("unrelated tool executed")

        monkeypatch.setattr(procurement_tools, "create_po_draft", spy)
        from app.agents.agent2_execution.tools.registry import registry

        registry._tools["create_po_draft"].handler = spy
        monkeypatch.setattr(notification_tools, "send_email", forbid)
        result = await _execute_po(harness, process_id, plan, po)
        assert result.execution_status == "SUCCESS"
        assert result.tool_name == "create_po_draft"
        assert result.implementation_key == "procurement.create_purchase_order"
        assert result.step_status == WorkflowStepStatus.COMPLETED.value
        assert result.receipt_id is not None
        assert len(calls) == 1
        assert other_tools == []
        refreshed = await harness["plans"].get_plan(plan.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        completed = [s.step_key for s in refreshed.steps if s.status is WorkflowStepStatus.COMPLETED]
        assert "create-purchase-order" in completed
        assert completed.count("create-purchase-order") == 1
        meta = get_memory_process_metadata(str(process_id))
        assert meta["purchase_order_ref"]["currency"] == "LKR"
        assert meta["purchase_order_ref"]["vendor_id"] == "vendor-it-01"
        record = get_procurement().get_purchase_order_for_process(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        )
        assert record is not None
        assert record.currency == "LKR"

    async def test_duplicate_execution_no_second_po(self, harness):
        process_id, plan = await _planned_process(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        po = _po_step(plan)
        first = await _execute_po(harness, process_id, plan, po, idempotency_key="po-once")
        second = await _execute_po(harness, process_id, plan, po, idempotency_key="po-once")
        assert first.receipt_id == second.receipt_id or second.duplicate is True
        drafts = get_memory_process_metadata(str(process_id)).get("purchase_order_ref")
        assert drafts is not None
        from app.procurement.service import get_procurement

        rows = get_procurement().repository.list_purchase_orders_for_process(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        )
        assert len(rows) == 1

    async def test_wrong_caller_action_ignored(self, harness):
        process_id, plan = await _planned_process(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        po = _po_step(plan)
        result = await _execute_po(
            harness,
            process_id,
            plan,
            po,
            caller_parameters={"tool_name": "send_email", "action": "SEND_EMAIL"},
        )
        assert result.tool_name == "create_po_draft"
        assert "send_email" not in str(get_memory_process_metadata(str(process_id)))

    async def test_wrong_tenant(self, harness):
        process_id, plan = await _planned_process(harness)
        po = _po_step(plan)
        with pytest.raises(CrossTenantDeniedError):
            await harness["executor"].execute_one_step(
                WorkflowStepExecutionRequest(
                    process_id=process_id,
                    workflow_plan_id=plan.id,
                    workflow_step_id=po.id,
                ),
                tenant_id=OTHER_TENANT,
            )

    async def test_conflicting_process_context(self, harness):
        process_id, plan = await _planned_process(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        po = _po_step(plan)
        with pytest.raises(ConflictingExecutionInputError):
            await _execute_po(
                harness,
                process_id,
                plan,
                po,
                caller_parameters={"amount": 2500, "currency": "USD"},
            )
        assert "purchase_order" not in get_memory_process_metadata(str(process_id))

    async def test_disabled_tool(self, harness):
        process_id, plan = await _planned_process(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        po = _po_step(plan)
        tools = await harness["tools"].list_tools(tenant_id=BPMFLOW_DEMO_TENANT_ID)
        registered = next(item for item in tools if item.tool_name == "create_purchase_order")
        await harness["tools"].disable_tool(registered.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        with pytest.raises(WorkflowStepExecutionError) as exc:
            await _execute_po(harness, process_id, plan, po)
        assert exc.value.error_code == "TOOL_DISABLED"
        await harness["tools"].enable_tool(registered.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        result = await _execute_po(harness, process_id, plan, po)
        assert result.execution_status == "SUCCESS"

    async def test_failed_tool_marks_step_failed(self, harness, monkeypatch):
        process_id, plan = await _planned_process(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        po = _po_step(plan)

        async def boom(session, data):
            raise RuntimeError("ERP unavailable")

        from app.agents.agent2_execution.tools.registry import registry

        registry._tools["create_po_draft"].handler = boom
        result = await _execute_po(harness, process_id, plan, po)
        assert result.execution_status == "FAILED"
        assert result.step_status == WorkflowStepStatus.FAILED.value
        refreshed = await harness["plans"].get_plan(plan.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        others = [
            step
            for step in refreshed.steps
            if step.step_key != "create-purchase-order"
            and step.status is WorkflowStepStatus.FAILED
        ]
        assert others == []

    async def test_concurrency_single_mutating_call(self, harness, monkeypatch):
        process_id, plan = await _planned_process(harness)
        plan = await _complete_predecessors(harness, plan, through_approvals=True)
        po = _po_step(plan)
        calls: list[int] = []
        from app.agents.agent2_execution.tools import procurement_tools
        from app.agents.agent2_execution.tools.registry import registry

        original = procurement_tools.create_po_draft

        async def counted(session, data):
            calls.append(1)
            await asyncio.sleep(0.05)
            return await original(session, data)

        registry._tools["create_po_draft"].handler = counted
        first, second = await asyncio.gather(
            _execute_po(harness, process_id, plan, po, idempotency_key="same-po"),
            _execute_po(harness, process_id, plan, po, idempotency_key="same-po"),
            return_exceptions=True,
        )
        successes = [item for item in (first, second) if not isinstance(item, Exception)]
        assert len(calls) == 1
        assert any(getattr(item, "execution_status", None) == "SUCCESS" for item in successes)

    async def test_full_task_suite_forbidden(self, harness):
        agent = Agent2(gemini_client=GeminiClient(is_offline=True))
        message = AgentMessage(
            message_id="msg-full",
            process_id=str(uuid4()),
            trace_id="trace-full",
            sender="agent_4",
            receiver="agent_2",
            task_type="EXECUTE_TASK",
            payload={
                "task_id": str(uuid4()),
                "parameters": {"tool_name": FULL_TASK_SUITE_TOOL},
                "tool_name": FULL_TASK_SUITE_TOOL,
            },
            status="AUTHORIZED",
        )
        response = await agent.handle(message, session=None)
        assert response.payload.get("receipt_status") == "BLOCKED"
        assert "FULL_WORKFLOW" in str(response.payload.get("error_message") or "").upper() or response.payload.get(
            "receipt_status"
        ) == "BLOCKED"
        assert (response.payload.get("tools_executed") or []) == []
