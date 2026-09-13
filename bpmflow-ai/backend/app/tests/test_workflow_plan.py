"""Phase 4 WorkflowPlan / WorkflowStep foundation tests. Definition only — no execution."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.agents.agent4_orchestrator.exceptions import ProcessNotFoundError
from app.agents.agent4_orchestrator.workflow_plan.constants import (
    WorkflowPlanStatus,
    WorkflowStepStatus,
    WorkflowStepType,
)
from app.agents.agent4_orchestrator.workflow_plan.exceptions import (
    DuplicateDependencyError,
    DuplicateStepKeyError,
    PlanNotMutableError,
    WorkflowPlanError,
)
from app.agents.agent4_orchestrator.workflow_plan.repository import (
    InMemoryWorkflowPlanRepository,
    SqlAlchemyWorkflowPlanRepository,
)
from app.agents.agent4_orchestrator.workflow_plan.schemas import (
    UNRESOLVED_RESPONSIBLE_PERSON,
    CreateWorkflowPlanInput,
    CreateWorkflowStepInput,
    WorkflowEvidenceRef,
    WorkflowPolicyRef,
)
from app.agents.agent4_orchestrator.workflow_plan.service import WorkflowPlanService
from app.company_directory.repository import InMemoryCompanyDirectoryRepository
from app.company_directory.seed import (
    BPMFLOW_DEMO_TENANT_ID,
    EMP_FINANCE_MANAGER,
    EMP_PROCUREMENT_OFFICER_1,
    RES_FINANCE_MANAGER,
    RES_PROCUREMENT_OFFICER_1,
    ROLE_FINANCE_MANAGER,
    ROLE_PROCUREMENT_OFFICER,
    DEPT_FINANCE,
    DEPT_PROCUREMENT,
    seed_bpmflow_demo_company,
)
from app.company_directory.service import CompanyDirectoryService
from app.core.database import Base
from app.schemas.agent_message import AGENT_2, AGENT_4, AgentMessage, AgentMessageMetadata, AgentMessageType

pytestmark = pytest.mark.asyncio

OTHER_TENANT = UUID("00000000-0000-0000-0000-00000000d099")
FOREIGN_EMPLOYEE = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


@pytest.fixture
def directory() -> CompanyDirectoryService:
    service = CompanyDirectoryService(InMemoryCompanyDirectoryRepository())
    seed_bpmflow_demo_company(service)
    return service


@pytest.fixture
async def svc(directory) -> WorkflowPlanService:
    repo = InMemoryWorkflowPlanRepository()
    return WorkflowPlanService(repo, directory=directory)


async def _bound_process(svc: WorkflowPlanService, tenant_id: UUID | None = None) -> UUID:
    process_id = uuid4()
    await svc._repo.register_process(
        process_id,
        tenant_id or BPMFLOW_DEMO_TENANT_ID,
        process_context_schema_version="1.0.0",
    )
    return process_id


def _human_step(
    *,
    step_key: str,
    sequence: int,
    name: str,
    step_type: WorkflowStepType,
    employee_id: UUID,
    resource_id: UUID | None = None,
    role_id: UUID | None = None,
    department_id: UUID | None = None,
    depends_on: list[str] | None = None,
    required_action: str = "REVIEW_DOCUMENT",
    required_tool_category: str | None = None,
    approval_required: bool = False,
    approval_type: str | None = None,
    recipients: list[UUID] | None = None,
    evidence: list[WorkflowEvidenceRef] | None = None,
    policies: list[WorkflowPolicyRef] | None = None,
    inputs: dict | None = None,
    expected_outputs: dict | None = None,
) -> CreateWorkflowStepInput:
    return CreateWorkflowStepInput(
        step_key=step_key,
        sequence=sequence,
        name=name,
        step_type=step_type,
        responsible_employee_id=employee_id,
        responsible_resource_id=resource_id,
        responsible_role_id=role_id,
        responsible_department_id=department_id,
        depends_on_step_keys=depends_on or [],
        required_action=required_action,
        required_tool_category=required_tool_category,
        approval_required=approval_required,
        approval_type=approval_type,
        recipient_employee_ids=recipients or [],
        evidence_refs=evidence or [],
        policy_refs=policies or [],
        inputs=inputs or {"process_context_ref": "process_context"},
        expected_outputs=expected_outputs or {"status": "recorded"},
    )


async def _draft(svc: WorkflowPlanService, process_id: UUID) -> UUID:
    plan = await svc.create_draft(
        CreateWorkflowPlanInput(process_id=process_id),
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
    )
    return plan.id


class TestWorkflowPlanCreate:
    async def test_create_workflow_plan(self, svc):
        process_id = await _bound_process(svc)
        plan = await svc.create_draft(
            CreateWorkflowPlanInput(process_id=process_id),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        assert plan.status is WorkflowPlanStatus.DRAFT
        assert plan.version == 1
        assert plan.created_by_agent == "agent4"
        assert plan.process_id == process_id
        assert plan.source_process_context_ref == "process_context"
        assert plan.source_process_context_schema_version == "1.0.0"

    async def test_unknown_process_rejected(self, svc):
        with pytest.raises(ProcessNotFoundError):
            await svc.create_draft(
                CreateWorkflowPlanInput(process_id=uuid4()),
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
            )


class TestWorkflowSteps:
    async def test_create_steps_and_ordering(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        await svc.add_step(
            plan_id,
            _human_step(
                step_key="review-pr",
                sequence=2,
                name="Review PR",
                step_type=WorkflowStepType.DOCUMENT_REVIEW,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        await svc.add_step(
            plan_id,
            _human_step(
                step_key="review-quote",
                sequence=1,
                name="Review quote",
                step_type=WorkflowStepType.VALIDATION,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        steps = await svc.list_steps(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert [step.step_key for step in steps] == ["review-quote", "review-pr"]
        assert all(step.status is WorkflowStepStatus.PENDING for step in steps)

    async def test_unique_step_keys(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        payload = _human_step(
            step_key="same",
            sequence=1,
            name="A",
            step_type=WorkflowStepType.HUMAN_TASK,
            employee_id=EMP_PROCUREMENT_OFFICER_1,
        )
        await svc.add_step(plan_id, payload, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        with pytest.raises(DuplicateStepKeyError):
            await svc.add_step(
                plan_id,
                _human_step(
                    step_key="same",
                    sequence=2,
                    name="B",
                    step_type=WorkflowStepType.HUMAN_TASK,
                    employee_id=EMP_PROCUREMENT_OFFICER_1,
                ),
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
            )


class TestDependencies:
    async def test_dependencies_recorded(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        await svc.add_step(
            plan_id,
            _human_step(
                step_key="s1",
                sequence=1,
                name="One",
                step_type=WorkflowStepType.DOCUMENT_REVIEW,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        await svc.add_step(
            plan_id,
            _human_step(
                step_key="s2",
                sequence=2,
                name="Two",
                step_type=WorkflowStepType.VALIDATION,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
                depends_on=["s1"],
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        plan = await svc.get_plan(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        by_key = {step.step_key: step for step in plan.steps}
        assert by_key["s2"].depends_on_step_keys == ["s1"]

    async def test_self_dependency_rejected(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        await svc.add_step(
            plan_id,
            _human_step(
                step_key="s1",
                sequence=1,
                name="One",
                step_type=WorkflowStepType.DOCUMENT_REVIEW,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        with pytest.raises(DuplicateDependencyError):
            await svc.add_dependency(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                workflow_plan_id=plan_id,
                step_key="s1",
                depends_on_step_key="s1",
            )

    async def test_duplicate_dependency_rejected(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        await svc.add_step(
            plan_id,
            _human_step(
                step_key="s1",
                sequence=1,
                name="One",
                step_type=WorkflowStepType.DOCUMENT_REVIEW,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        await svc.add_step(
            plan_id,
            _human_step(
                step_key="s2",
                sequence=2,
                name="Two",
                step_type=WorkflowStepType.VALIDATION,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
                depends_on=["s1"],
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        with pytest.raises(DuplicateDependencyError):
            await svc.add_dependency(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                workflow_plan_id=plan_id,
                step_key="s2",
                depends_on_step_key="s1",
            )

    async def test_cycle_rejected_on_validate(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        await svc.add_step(
            plan_id,
            _human_step(
                step_key="s1",
                sequence=1,
                name="One",
                step_type=WorkflowStepType.DOCUMENT_REVIEW,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        await svc.add_step(
            plan_id,
            _human_step(
                step_key="s2",
                sequence=2,
                name="Two",
                step_type=WorkflowStepType.VALIDATION,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
                depends_on=["s1"],
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        await svc.add_dependency(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            workflow_plan_id=plan_id,
            step_key="s1",
            depends_on_step_key="s2",
        )
        result = await svc.validate(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert not result.valid
        assert "DEPENDENCY_CYCLE" in _codes(result)

    async def test_cross_tenant_dependency_rejected(self, svc):
        process_a = await _bound_process(svc, BPMFLOW_DEMO_TENANT_ID)
        process_b = await _bound_process(svc, OTHER_TENANT)
        plan_a = await _draft(svc, process_a)
        plan_b = await svc.create_draft(
            CreateWorkflowPlanInput(process_id=process_b), tenant_id=OTHER_TENANT
        )
        await svc.add_step(
            plan_a,
            _human_step(
                step_key="s1",
                sequence=1,
                name="One",
                step_type=WorkflowStepType.DOCUMENT_REVIEW,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        await svc.add_step(
            plan_b.id,
            CreateWorkflowStepInput(
                step_key="s2",
                sequence=1,
                name="Other tenant step",
                step_type=WorkflowStepType.SYSTEM_ACTION,
                required_action="NOOP",
                required_tool_category="PROCUREMENT",
            ),
            tenant_id=OTHER_TENANT,
        )
        from app.agents.agent4_orchestrator.workflow_plan.exceptions import WorkflowStepNotFoundError

        with pytest.raises(WorkflowStepNotFoundError):
            await svc.add_dependency(
                tenant_id=OTHER_TENANT,
                workflow_plan_id=plan_b.id,
                step_key="s2",
                depends_on_step_key="s1",
            )


class TestAssignmentAndTenancy:
    async def test_cross_tenant_employee_rejected(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        await svc.add_step(
            plan_id,
            CreateWorkflowStepInput(
                step_key="approve",
                sequence=1,
                name="Approve",
                step_type=WorkflowStepType.APPROVAL,
                responsible_employee_id=FOREIGN_EMPLOYEE,
                required_action="REQUEST_APPROVAL",
                required_tool_category="COMMUNICATION",
                approval_required=True,
                approval_type="FINANCE",
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        result = await svc.validate(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert "CROSS_TENANT_DENIED" in _codes(result)

    async def test_employee_resource_mapping_validation(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        await svc.add_step(
            plan_id,
            _human_step(
                step_key="approve",
                sequence=1,
                name="Finance approval",
                step_type=WorkflowStepType.APPROVAL,
                employee_id=EMP_FINANCE_MANAGER,
                resource_id=RES_PROCUREMENT_OFFICER_1,
                role_id=ROLE_FINANCE_MANAGER,
                department_id=DEPT_FINANCE,
                required_action="REQUEST_APPROVAL",
                required_tool_category="COMMUNICATION",
                approval_required=True,
                approval_type="FINANCE",
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        result = await svc.validate(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert "EMPLOYEE_RESOURCE_MISMATCH" in _codes(result)

    async def test_missing_responsible_employee(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        await svc.add_step(
            plan_id,
            CreateWorkflowStepInput(
                step_key="review",
                sequence=1,
                name="Review",
                step_type=WorkflowStepType.DOCUMENT_REVIEW,
                assignment_unresolved=True,
                unresolved_reason=UNRESOLVED_RESPONSIBLE_PERSON,
                required_action="REVIEW_DOCUMENT",
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        result = await svc.validate(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert UNRESOLVED_RESPONSIBLE_PERSON in _codes(result)
        with pytest.raises(WorkflowPlanError):
            await svc.activate(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)

    async def test_communication_recipient_tenant(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        await svc.add_step(
            plan_id,
            CreateWorkflowStepInput(
                step_key="notify",
                sequence=1,
                name="Notify finance",
                step_type=WorkflowStepType.COMMUNICATION,
                responsible_employee_id=EMP_PROCUREMENT_OFFICER_1,
                required_action="SEND_NOTIFICATION",
                required_tool_category="COMMUNICATION",
                recipient_employee_ids=[FOREIGN_EMPLOYEE],
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        result = await svc.validate(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert "CROSS_TENANT_DENIED" in _codes(result)


class TestStepDeclarations:
    async def test_approval_metadata_required(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        await svc.add_step(
            plan_id,
            CreateWorkflowStepInput(
                step_key="approve",
                sequence=1,
                name="Approve",
                step_type=WorkflowStepType.APPROVAL,
                responsible_employee_id=EMP_FINANCE_MANAGER,
                required_action="REQUEST_APPROVAL",
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        result = await svc.validate(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert "APPROVAL_METADATA_MISSING" in _codes(result)

    async def test_required_action_and_tool_category(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        await svc.add_step(
            plan_id,
            CreateWorkflowStepInput(
                step_key="po",
                sequence=1,
                name="Create PO",
                step_type=WorkflowStepType.SYSTEM_ACTION,
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        result = await svc.validate(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert "REQUIRED_ACTION_MISSING" in _codes(result)
        assert "REQUIRED_TOOL_CATEGORY_MISSING" in _codes(result)

    async def test_evidence_and_policy_refs_preserved(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        evidence = [WorkflowEvidenceRef(evidence_id="quotation-PR-2026-0098-q1", kind="quotation")]
        policies = [WorkflowPolicyRef(policy_id="PROC-POL-001", policy_version="2026.1")]
        await svc.add_step(
            plan_id,
            _human_step(
                step_key="review-quote",
                sequence=1,
                name="Review quotation evidence",
                step_type=WorkflowStepType.VALIDATION,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
                resource_id=RES_PROCUREMENT_OFFICER_1,
                evidence=evidence,
                policies=policies,
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        steps = await svc.list_steps(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert steps[0].evidence_refs[0].evidence_id == "quotation-PR-2026-0098-q1"
        assert steps[0].policy_refs[0].policy_id == "PROC-POL-001"
        assert steps[0].policy_refs[0].policy_version == "2026.1"

    async def test_process_context_relationship(self, svc):
        process_id = await _bound_process(svc)
        plan = await svc.create_draft(
            CreateWorkflowPlanInput(
                process_id=process_id,
                source_process_context_schema_version="1.0.0",
                source_process_context_ref="process_context",
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        assert plan.process_id == process_id
        assert plan.source_process_context_ref == "process_context"
        loaded = await svc.get_plan(plan.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert loaded.process_id == process_id


class TestVersioningAndActivation:
    async def test_versioning_and_supersede(self, svc):
        process_id = await _bound_process(svc)
        v1_id = await _draft(svc, process_id)
        await _add_valid_system_step(svc, v1_id)
        activated = await svc.activate(v1_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert activated.status is WorkflowPlanStatus.ACTIVE
        v2 = await svc.create_draft(
            CreateWorkflowPlanInput(process_id=process_id),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        assert v2.version == 2
        await _add_valid_system_step(svc, v2.id)
        second = await svc.activate(v2.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert second.status is WorkflowPlanStatus.ACTIVE
        previous = await svc.get_plan(v1_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert previous.status is WorkflowPlanStatus.SUPERSEDED
        by_version = await svc.get_plan_version(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id, version=1
        )
        assert by_version is not None
        assert by_version.status is WorkflowPlanStatus.SUPERSEDED
        active = await svc.get_active_plan(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        )
        assert active is not None
        assert active.id == v2.id

    async def test_invalid_plan_cannot_activate(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        with pytest.raises(WorkflowPlanError):
            await svc.activate(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)

    async def test_cannot_silently_overwrite_active_plan(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        await _add_valid_system_step(svc, plan_id)
        await svc.activate(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        with pytest.raises(PlanNotMutableError):
            await svc.add_step(
                plan_id,
                CreateWorkflowStepInput(
                    step_key="extra",
                    sequence=2,
                    name="Extra",
                    step_type=WorkflowStepType.SYSTEM_ACTION,
                    required_action="NOOP",
                    required_tool_category="PROCUREMENT",
                ),
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
            )

    async def test_tenant_isolation(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        from app.agents.agent4_orchestrator.workflow_plan.exceptions import WorkflowPlanNotFoundError

        with pytest.raises(WorkflowPlanNotFoundError):
            await svc.get_plan(plan_id, tenant_id=OTHER_TENANT)

    async def test_approval_step_not_auto_completed(self, svc):
        process_id = await _bound_process(svc)
        plan_id = await _draft(svc, process_id)
        await svc.add_step(
            plan_id,
            _human_step(
                step_key="approve",
                sequence=1,
                name="Finance approval",
                step_type=WorkflowStepType.APPROVAL,
                employee_id=EMP_FINANCE_MANAGER,
                resource_id=RES_FINANCE_MANAGER,
                role_id=ROLE_FINANCE_MANAGER,
                department_id=DEPT_FINANCE,
                required_action="REQUEST_APPROVAL",
                required_tool_category="COMMUNICATION",
                approval_required=True,
                approval_type="FINANCE",
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        activated = await svc.activate(plan_id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        step = activated.steps[0]
        assert step.approval_required is True
        assert step.status is not WorkflowStepStatus.COMPLETED
        assert step.status in {WorkflowStepStatus.PENDING, WorkflowStepStatus.READY}


async def _add_valid_system_step(svc: WorkflowPlanService, plan_id: UUID) -> None:
    await svc.add_step(
        plan_id,
        CreateWorkflowStepInput(
            step_key="create-po",
            sequence=1,
            name="Create purchase order",
            step_type=WorkflowStepType.SYSTEM_ACTION,
            responsible_employee_id=EMP_PROCUREMENT_OFFICER_1,
            responsible_resource_id=RES_PROCUREMENT_OFFICER_1,
            required_action="CREATE_PURCHASE_ORDER",
            required_tool_category="PROCUREMENT",
            inputs={"amount_ref": "process_context.purchase.amount"},
            expected_outputs={"purchase_order_id": None},
        ),
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
    )


class TestProcurementExample:
    async def test_procurement_plan_pr_2026_0098(self, svc):
        process_id = await _bound_process(svc)
        plan = await svc.create_draft(
            CreateWorkflowPlanInput(process_id=process_id),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        evidence = [
            WorkflowEvidenceRef(evidence_id="pr-2026-0098-request", kind="purchase_request"),
            WorkflowEvidenceRef(evidence_id="pr-2026-0098-quotation", kind="quotation"),
        ]
        policies = [WorkflowPolicyRef(policy_id="PROC-POL-001", policy_version="2026.1")]
        await svc.add_step(
            plan.id,
            _human_step(
                step_key="review-purchase-request",
                sequence=1,
                name="Review purchase request",
                step_type=WorkflowStepType.DOCUMENT_REVIEW,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
                resource_id=RES_PROCUREMENT_OFFICER_1,
                role_id=ROLE_PROCUREMENT_OFFICER,
                department_id=DEPT_PROCUREMENT,
                required_action="REVIEW_DOCUMENT",
                evidence=evidence[:1],
                policies=policies,
                inputs={
                    "process_id": str(process_id),
                    "request_ref": "process_context.purchase.purchase_request_id",
                },
                expected_outputs={"review_status": None},
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        await svc.add_step(
            plan.id,
            _human_step(
                step_key="review-quotation-evidence",
                sequence=2,
                name="Review quotation evidence",
                step_type=WorkflowStepType.VALIDATION,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
                resource_id=RES_PROCUREMENT_OFFICER_1,
                role_id=ROLE_PROCUREMENT_OFFICER,
                department_id=DEPT_PROCUREMENT,
                depends_on=["review-purchase-request"],
                required_action="VALIDATE_EVIDENCE",
                evidence=evidence[1:],
                policies=policies,
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        await svc.add_step(
            plan.id,
            _human_step(
                step_key="finance-approval",
                sequence=3,
                name="Finance approval",
                step_type=WorkflowStepType.APPROVAL,
                employee_id=EMP_FINANCE_MANAGER,
                resource_id=RES_FINANCE_MANAGER,
                role_id=ROLE_FINANCE_MANAGER,
                department_id=DEPT_FINANCE,
                depends_on=["review-quotation-evidence"],
                required_action="REQUEST_APPROVAL",
                required_tool_category="COMMUNICATION",
                approval_required=True,
                approval_type="FINANCE",
                recipients=[EMP_FINANCE_MANAGER],
                evidence=evidence,
                policies=policies,
                inputs={
                    "process_id": str(process_id),
                    "amount_ref": "process_context.purchase.amount",
                    "currency_ref": "process_context.purchase.currency",
                    "requester_ref": "process_context.requester",
                },
                expected_outputs={
                    "approval_decision": None,
                    "approver_employee_id": None,
                    "timestamp": None,
                    "audit_receipt": None,
                },
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        await svc.add_step(
            plan.id,
            _human_step(
                step_key="create-purchase-order",
                sequence=4,
                name="Create purchase order",
                step_type=WorkflowStepType.SYSTEM_ACTION,
                employee_id=EMP_PROCUREMENT_OFFICER_1,
                resource_id=RES_PROCUREMENT_OFFICER_1,
                role_id=ROLE_PROCUREMENT_OFFICER,
                department_id=DEPT_PROCUREMENT,
                depends_on=["finance-approval"],
                required_action="CREATE_PURCHASE_ORDER",
                required_tool_category="PROCUREMENT",
                evidence=evidence,
                policies=policies,
                inputs={
                    "vendor_ref": "process_context.purchase.vendor_id",
                    "approved_amount_ref": "process_context.purchase.amount",
                    "quotation_evidence": "pr-2026-0098-quotation",
                },
                expected_outputs={"purchase_order_id": None, "creation_receipt": None},
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        result = await svc.validate(plan.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        assert result.valid, result.issues
        activated = await svc.activate(plan.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
        by_key = {step.step_key: step for step in activated.steps}
        assert by_key["finance-approval"].responsible_employee_id == EMP_FINANCE_MANAGER
        assert by_key["finance-approval"].responsible_resource_id == RES_FINANCE_MANAGER
        assert by_key["create-purchase-order"].required_action == "CREATE_PURCHASE_ORDER"
        assert by_key["create-purchase-order"].required_tool_category == "PROCUREMENT"
        assert by_key["finance-approval"].status is not WorkflowStepStatus.COMPLETED
        assert all(step.status is not WorkflowStepStatus.COMPLETED for step in activated.steps)


class TestSqlAlchemyPersistence:
    async def test_plan_round_trips_through_sqlite(self, directory):
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as session:
            repo = SqlAlchemyWorkflowPlanRepository(session)
            svc = WorkflowPlanService(repo, directory=directory)
            process_id = uuid4()
            await repo.register_process(
                process_id, BPMFLOW_DEMO_TENANT_ID, process_context_schema_version="1.0.0"
            )
            plan = await svc.create_draft(
                CreateWorkflowPlanInput(process_id=process_id),
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
            )
            await svc.add_step(
                plan.id,
                CreateWorkflowStepInput(
                    step_key="create-po",
                    sequence=1,
                    name="Create purchase order",
                    step_type=WorkflowStepType.SYSTEM_ACTION,
                    required_action="CREATE_PURCHASE_ORDER",
                    required_tool_category="PROCUREMENT",
                    evidence_refs=[
                        WorkflowEvidenceRef(evidence_id="pr-2026-0098-quotation", kind="quotation")
                    ],
                    policy_refs=[
                        WorkflowPolicyRef(policy_id="PROC-POL-001", policy_version="2026.1")
                    ],
                ),
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
            )
            await session.commit()

        async with factory() as session:
            repo = SqlAlchemyWorkflowPlanRepository(session)
            loaded = await repo.get_plan(plan.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
            assert loaded.version == 1
            assert loaded.steps[0].step_key == "create-po"
            assert loaded.steps[0].evidence_refs[0].evidence_id == "pr-2026-0098-quotation"
            assert loaded.steps[0].status is WorkflowStepStatus.PENDING
        await engine.dispose()


class TestAgentMessageReferences:
    async def test_envelope_can_reference_plan_and_step_ids(self):
        plan_id = uuid4()
        step_id = uuid4()
        message = AgentMessage(
            metadata=AgentMessageMetadata(
                correlation_id=uuid4(),
                process_instance_id=uuid4(),
                sender=AGENT_4,
                receiver=AGENT_2,
                message_type=AgentMessageType.WORKFLOW_EXECUTION_REQUEST,
                workflow_plan_id=plan_id,
                workflow_step_id=step_id,
            ),
            payload={"workflow_plan_id": str(plan_id), "workflow_step_id": str(step_id)},
        )
        assert message.metadata.workflow_plan_id == plan_id
        assert message.payload["workflow_plan_id"] == str(plan_id)
