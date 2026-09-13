"""Phase 6 Agent 4 deterministic workflow planning. No tool execution."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.agents.agent3_resources.interfaces import InMemoryResourceRepository
from app.agents.agent3_resources.service import ResourceAllocationService
from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository
from app.agents.agent4_orchestrator.workflow_plan.constants import WorkflowPlanStatus
from app.agents.agent4_orchestrator.workflow_plan.planner import WorkflowPlanner
from app.agents.agent4_orchestrator.workflow_plan.repository import InMemoryWorkflowPlanRepository
from app.agents.agent4_orchestrator.workflow_plan.service import WorkflowPlanService
from app.company_directory.repository import InMemoryCompanyDirectoryRepository
from app.company_directory.seed import (
    AUTH_USER_FINANCE_MANAGER,
    AUTH_USER_REQUESTER,
    BPMFLOW_DEMO_TENANT_ID,
    EMP_FINANCE_MANAGER,
    EMP_PROCUREMENT_OFFICER_1,
    EMP_SENIOR_MANAGER,
    RES_FINANCE_MANAGER,
    RES_PROCUREMENT_OFFICER_1,
    RES_SENIOR_MANAGER,
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
from app.process_context.schemas import (
    BudgetFacts,
    EvidenceItem,
    ProcessContext,
    PurchaseFacts,
    QuotationFact,
    RequesterIdentity,
)
from app.tool_registry.constants import ToolActionCode, ToolCategory
from app.tool_registry.repository import InMemoryToolRegistryRepository
from app.tool_registry.schemas import RegisterToolInput
from app.tool_registry.seed import seed_bpmflow_tool_registry
from app.tool_registry.service import ToolRegistryService

pytestmark = pytest.mark.asyncio

OTHER_TENANT = UUID("00000000-0000-0000-0000-00000000d099")
OBJECT_SCHEMA = {"type": "object", "properties": {}}


async def _seed_policy(ingestion: PolicyIngestionService, tenant_id: UUID) -> None:
    await ingestion.ingest(
        tenant_id=tenant_id,
        uploaded_by=uuid4(),
        request=PolicyCreateRequest(
            name="BPMFlow Procurement Policy",
            category=PolicyCategory.PROCUREMENT,
            version_label="2026.1",
            activate=True,
            text_content=(
                "Purchases up to 100000 LKR require Manager approval. "
                "Purchases above 100000 LKR require Finance approval. "
                "Purchases above 1000000 LKR require Senior Management and Finance. "
                "Quotations are required above 100000 LKR. Two quotations above 1000000 LKR."
            ),
            rules=[
                PolicyRule(
                    rule_type=PolicyRuleType.APPROVAL_THRESHOLD,
                    operator=PolicyOperator.GT,
                    threshold_value=Decimal("1000000"),
                    currency="LKR",
                    required_approval="SENIOR_MANAGEMENT",
                    metadata_json={
                        "additional_approvals": [
                            {"applies_at_or_below": "100000", "approval": "MANAGER"},
                            {"applies_above": "100000", "approval": "FINANCE"},
                            {"applies_above": "1000000", "approval": "SENIOR_MANAGEMENT"},
                        ]
                    },
                ),
                PolicyRule(
                    rule_type=PolicyRuleType.HIGH_VALUE_THRESHOLD,
                    operator=PolicyOperator.GT,
                    threshold_value=Decimal("1000000"),
                    currency="LKR",
                    required_approval="SENIOR_MANAGEMENT",
                ),
                PolicyRule(
                    rule_type=PolicyRuleType.REQUIRED_EVIDENCE,
                    required_evidence=["quotation"],
                    metadata_json={"min_quotations": 1, "applies_above": "100000"},
                ),
                PolicyRule(
                    rule_type=PolicyRuleType.REQUIRED_EVIDENCE,
                    required_evidence=["quotation"],
                    metadata_json={
                        "min_quotations": 2,
                        "applies_above": "1000000",
                        "requires_justification": True,
                        "requires_budget_confirmation": True,
                    },
                ),
                PolicyRule(rule_type=PolicyRuleType.SEGREGATION_OF_DUTIES),
            ],
        ),
    )


def _ctx(
    process_id: UUID,
    *,
    amount: str,
    budget: str,
    quotes: int,
    requester_user: UUID = AUTH_USER_REQUESTER,
    description: str = "PR-2026-0098 laptop refresh",
    vendor_id: str = "vendor-it-01",
) -> ProcessContext:
    quotations = [
        QuotationFact(
            quotation_id=f"q-{index}",
            vendor=f"Vendor {index}",
            amount=Decimal(amount),
            currency="LKR",
            evidence_id=f"quotation-{index}",
        )
        for index in range(1, quotes + 1)
    ]
    return ProcessContext(
        process_id=process_id,
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
        requester=RequesterIdentity(user_id=requester_user, identity_mapped=True),
        purchase=PurchaseFacts(
            description=description,
            amount=Decimal(amount),
            currency="LKR",
            vendor_id=vendor_id,
            purchase_request_id="PR-2026-0098" if "0098" in description else "PR-2026-0105",
            amount_source="extracted_evidence",
        ),
        budget=BudgetFacts(
            available_amount=Decimal(budget),
            currency="LKR",
            source="company_repository",
        ),
        quotations=quotations,
        evidence=[
            EvidenceItem(evidence_id="purchase-request", type="purchase_request"),
            *[
                EvidenceItem(evidence_id=f"quotation-{index}", type="quotation")
                for index in range(1, quotes + 1)
            ],
        ],
    )


@pytest.fixture
async def harness():
    directory = CompanyDirectoryService(InMemoryCompanyDirectoryRepository())
    seed_bpmflow_demo_company(directory)
    processes = InMemoryProcessRepository()
    plans = WorkflowPlanService(InMemoryWorkflowPlanRepository(), directory=directory)
    tools = ToolRegistryService(InMemoryToolRegistryRepository())
    await seed_bpmflow_tool_registry(tools, tenant_id=BPMFLOW_DEMO_TENANT_ID)
    policy_repo = InMemoryPolicyRepository()
    ingestion = PolicyIngestionService(policy_repo)
    await _seed_policy(ingestion, BPMFLOW_DEMO_TENANT_ID)
    planner = WorkflowPlanner(
        plan_service=plans,
        process_repository=processes,
        policy_retrieval=PolicyRetrievalService(policy_repo),
        tool_registry=tools,
        directory=directory,
        allocator=ResourceAllocationService(InMemoryResourceRepository(), directory=directory),
    )
    return {
        "directory": directory,
        "processes": processes,
        "plans": plans,
        "tools": tools,
        "planner": planner,
        "policy_repo": policy_repo,
    }


async def _process_with_context(harness, ctx: ProcessContext, *, name: str):
    record = await harness["processes"].insert_process(
        name=name,
        process_type="procurement",
        description=ctx.purchase.description,
        created_by=ctx.requester.user_id,
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
    )
    ctx = ctx.model_copy(update={"process_id": record.id})
    harness["processes"]._records[record.id] = record.model_copy(
        update={"process_context": ctx.model_dump(mode="json")}
    )
    return record.id, ctx


class TestWorkflowPlanning:
    async def test_basic_and_procurement_generation(self, harness):
        process_id, ctx = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="PR-2026-0098"
        )
        result = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        keys = [step.step_key for step in result.steps]
        assert "review-purchase-request" in keys
        assert "validate-quotations" in keys
        assert "finance-approval" in keys
        assert "senior-management-approval" in keys
        assert "create-purchase-order" in keys
        assert result.status == WorkflowPlanStatus.READY.value
        assert result.plan.status is not WorkflowPlanStatus.ACTIVE
        _ = ctx

    async def test_agent3_real_employee_and_resource_assignment(self, harness):
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="PR-2026-0098"
        )
        result = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        by_key = {step.step_key: step for step in result.steps}
        review = by_key["review-purchase-request"]
        assert review.responsible_employee_id == EMP_PROCUREMENT_OFFICER_1
        assert review.responsible_resource_id == RES_PROCUREMENT_OFFICER_1
        finance = by_key["finance-approval"]
        assert finance.responsible_employee_id == EMP_FINANCE_MANAGER
        assert finance.responsible_resource_id == RES_FINANCE_MANAGER
        senior = by_key["senior-management-approval"]
        assert senior.responsible_employee_id == EMP_SENIOR_MANAGER
        assert senior.responsible_resource_id == RES_SENIOR_MANAGER
        assert finance.status.value == "WAITING_HUMAN_APPROVAL"
        assert finance.approval_required is True

    async def test_policy_driven_approvals_and_dependencies(self, harness):
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="PR-2026-0098"
        )
        result = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        by_key = {step.step_key: step for step in result.steps}
        assert by_key["validate-quotations"].depends_on_step_keys == ["review-purchase-request"]
        assert by_key["finance-approval"].depends_on_step_keys == ["validate-quotations"]
        assert by_key["create-purchase-order"].depends_on_step_keys[-1] == "senior-management-approval"

    async def test_process_context_facts_preserved(self, harness):
        process_id, ctx = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="PR-2026-0098"
        )
        result = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        loaded = await harness["processes"].get_process(process_id)
        stored = ProcessContext.model_validate(loaded.process_context)
        assert stored.purchase.amount == Decimal("1500000")
        assert stored.purchase.currency == "LKR"
        assert stored.purchase.vendor_id == ctx.purchase.vendor_id
        po = next(step for step in result.steps if step.step_key == "create-purchase-order")
        assert po.inputs["amount_ref"] == "process_context.purchase.amount"
        assert "1500000" not in str(po.inputs.get("amount", ""))

    async def test_tool_registry_po_resolution(self, harness):
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="PR-2026-0098"
        )
        result = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        po = next(step for step in result.steps if step.required_action == "CREATE_PURCHASE_ORDER")
        assert po.inputs["tool_resolution"]["status"] == "RESOLVED"
        assert po.inputs["tool_resolution"]["tool_name"] == "create_purchase_order"
        assert po.inputs["tool_resolution"]["implementation_key"] == "procurement.create_purchase_order"
        assert po.inputs["tool_resolution"]["agent2_tool_name"] == "create_po_draft"
        match = next(step for step in result.steps if step.required_action == "MATCH_INVOICE")
        assert match.inputs["tool_resolution"]["status"] == "RESOLVED"
        assert match.inputs["tool_resolution"]["agent2_tool_name"] == "match_invoice"
        assert match.inputs["tool_resolution"]["implementation_key"] == "procurement.match_invoice"
        assert result.execution_ready is False
        assert any(issue.code == "TOOL_NOT_REGISTERED" for issue in result.issues)

    async def test_high_value_pr_2026_0098(self, harness):
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="PR-2026-0098"
        )
        result = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        codes = {issue.code for issue in result.blocking_errors}
        assert "INSUFFICIENT_BUDGET" not in codes
        assert "SAME_PERSON" not in codes
        assert result.structurally_valid is True

    async def test_policy_violation_pr_2026_0105(self, harness):
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
        codes = {issue.code for issue in result.issues}
        assert "INSUFFICIENT_BUDGET" in codes
        assert "MISSING_REQUIRED_CONTEXT" in codes
        assert "SAME_PERSON" in codes
        assert result.status == WorkflowPlanStatus.DRAFT.value
        assert result.execution_ready is False
        with pytest.raises(Exception):
            await harness["plans"].activate(result.workflow_plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)

    async def test_missing_context_and_policy(self, harness):
        record = await harness["processes"].insert_process(
            name="empty", process_type="procurement", tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        missing = await harness["planner"].generate_plan(
            process_id=record.id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        assert any(issue.code == "MISSING_REQUIRED_CONTEXT" for issue in missing.issues)

        planner = WorkflowPlanner(
            plan_service=harness["plans"],
            process_repository=harness["processes"],
            policy_retrieval=PolicyRetrievalService(InMemoryPolicyRepository()),
            tool_registry=harness["tools"],
            directory=harness["directory"],
            allocator=ResourceAllocationService(
                InMemoryResourceRepository(), directory=harness["directory"]
            ),
        )
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="no-policy"
        )
        result = await planner.generate_plan(process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert any(issue.code == "POLICY_NOT_FOUND" for issue in result.issues)
        assert result.execution_ready is False

    async def test_no_eligible_resource_and_missing_approver(self, harness):
        empty = CompanyDirectoryService(InMemoryCompanyDirectoryRepository())
        planner = WorkflowPlanner(
            plan_service=WorkflowPlanService(InMemoryWorkflowPlanRepository(), directory=empty),
            process_repository=harness["processes"],
            policy_retrieval=PolicyRetrievalService(harness["policy_repo"]),
            tool_registry=harness["tools"],
            directory=empty,
            allocator=ResourceAllocationService(InMemoryResourceRepository(), directory=empty),
        )
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="no-people"
        )
        result = await planner.generate_plan(process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        codes = {issue.code for issue in result.issues}
        assert "NO_ELIGIBLE_RESOURCE" in codes or "APPROVER_NOT_RESOLVED" in codes
        assert result.execution_ready is False

        weird_policy = InMemoryPolicyRepository()
        ingestion = PolicyIngestionService(weird_policy)
        await ingestion.ingest(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            uploaded_by=uuid4(),
            request=PolicyCreateRequest(
                name="Odd",
                category=PolicyCategory.PROCUREMENT,
                version_label="x",
                activate=True,
                text_content="Requires BOARD approval above 1",
                rules=[
                    PolicyRule(
                        rule_type=PolicyRuleType.APPROVAL_THRESHOLD,
                        operator=PolicyOperator.GT,
                        threshold_value=Decimal("1"),
                        currency="LKR",
                        required_approval="BOARD",
                    ),
                ],
            ),
        )
        planner2 = WorkflowPlanner(
            plan_service=harness["plans"],
            process_repository=harness["processes"],
            policy_retrieval=PolicyRetrievalService(weird_policy),
            tool_registry=harness["tools"],
            directory=harness["directory"],
            allocator=ResourceAllocationService(
                InMemoryResourceRepository(), directory=harness["directory"]
            ),
        )
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="board"
        )
        result = await planner2.generate_plan(process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert any(issue.code == "APPROVER_NOT_RESOLVED" for issue in result.issues)

    async def test_disabled_and_missing_and_mismatch_tools(self, harness):
        tools = await harness["tools"].list_tools(tenant_id=BPMFLOW_DEMO_TENANT_ID)
        po = next(item for item in tools if item.action_code is ToolActionCode.CREATE_PURCHASE_ORDER)
        await harness["tools"].disable_tool(po.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="disabled-po"
        )
        disabled = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        assert any(issue.code == "TOOL_DISABLED" for issue in disabled.issues)

        empty_tools = ToolRegistryService(InMemoryToolRegistryRepository())
        planner = WorkflowPlanner(
            plan_service=harness["plans"],
            process_repository=harness["processes"],
            policy_retrieval=PolicyRetrievalService(harness["policy_repo"]),
            tool_registry=empty_tools,
            directory=harness["directory"],
            allocator=ResourceAllocationService(
                InMemoryResourceRepository(), directory=harness["directory"]
            ),
        )
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="no-tools"
        )
        missing = await planner.generate_plan(process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert any(issue.code == "TOOL_NOT_REGISTERED" for issue in missing.issues)

        mismatch = ToolRegistryService(InMemoryToolRegistryRepository())
        await mismatch.register_tool(
            RegisterToolInput(
                tool_name="create_purchase_order",
                tool_category=ToolCategory.COMMUNICATION,
                action_code=ToolActionCode.CREATE_PURCHASE_ORDER,
                implementation_key="procurement.create_purchase_order",
                allowed_step_types=["SYSTEM_ACTION"],
                input_schema=OBJECT_SCHEMA,
                output_schema=OBJECT_SCHEMA,
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        planner = WorkflowPlanner(
            plan_service=harness["plans"],
            process_repository=harness["processes"],
            policy_retrieval=PolicyRetrievalService(harness["policy_repo"]),
            tool_registry=mismatch,
            directory=harness["directory"],
            allocator=ResourceAllocationService(
                InMemoryResourceRepository(), directory=harness["directory"]
            ),
        )
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="mismatch"
        )
        result = await planner.generate_plan(process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert any(issue.code == "TOOL_CATEGORY_MISMATCH" for issue in result.issues)

    async def test_versioning_does_not_overwrite_active(self, harness):
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="PR-2026-0098"
        )
        first = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        activated = await harness["plans"].activate(
            first.workflow_plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        assert activated.status is WorkflowPlanStatus.ACTIVE
        second = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        assert second.version == 2
        assert second.status != WorkflowPlanStatus.ACTIVE.value
        still_active = await harness["plans"].get_active_plan(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        )
        assert still_active is not None
        assert still_active.id == first.workflow_plan_id

    async def test_no_invented_skills_or_defaults(self, harness):
        seen: list[list[str]] = []

        class Spy(ResourceAllocationService):
            async def process_allocation_request(self, request, evaluation_timestamp=None):
                if request.human_requirements:
                    seen.append(list(request.human_requirements.mandatory_skills))
                    seen.append(list(request.human_requirements.required_roles))
                return await super().process_allocation_request(
                    request, evaluation_timestamp=evaluation_timestamp
                )

        planner = WorkflowPlanner(
            plan_service=harness["plans"],
            process_repository=harness["processes"],
            policy_retrieval=PolicyRetrievalService(harness["policy_repo"]),
            tool_registry=harness["tools"],
            directory=harness["directory"],
            allocator=Spy(InMemoryResourceRepository(), directory=harness["directory"]),
        )
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="skills"
        )
        await planner.generate_plan(process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        flat = [item.lower() for group in seen for item in group]
        assert "python" not in flat
        assert "fastapi" not in flat
        assert "developer" not in flat
        assert "Procurement Officer" in {item for group in seen for item in group}

    async def test_tenant_isolation(self, harness):
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="tenant-a"
        )
        result = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=OTHER_TENANT
        )
        assert any(issue.code == "CROSS_TENANT_DENIED" for issue in result.issues)
        assert result.workflow_plan_id is None

    async def test_planning_does_not_execute_tools(self, harness, monkeypatch):
        calls: list[str] = []

        async def _forbid(*args, **kwargs):
            calls.append("executed")
            raise AssertionError("Agent 2 tools must not run during planning")

        from app.agents.agent2_execution.tools import procurement_tools
        from app.agents.agent4_orchestrator.workflow import Agent4Workflow

        monkeypatch.setattr(Agent4Workflow, "execute_authorized", _forbid)
        monkeypatch.setattr(Agent4Workflow, "execute_workflow", _forbid)
        monkeypatch.setattr(procurement_tools, "create_po_draft", _forbid)
        process_id, _ = await _process_with_context(
            harness, _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2), name="PR-2026-0098"
        )
        result = await harness["planner"].generate_plan(
            process_id=process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        po = next(step for step in result.steps if step.step_key == "create-purchase-order")
        assert po.status.value == "PENDING"
        assert result.plan.status is not WorkflowPlanStatus.ACTIVE
        assert calls == []
