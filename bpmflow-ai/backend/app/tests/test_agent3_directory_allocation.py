"""Phase 3: Agent 3 company-directory resource intelligence."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from inspect import getsource
from uuid import uuid4

import pytest

from app.agents.agent3_resources.constants import ExclusionReason, FailureErrorCode
from app.agents.agent3_resources.eligibility import EligibilityEvaluator
from app.agents.agent3_resources.fixtures import (
    FIXTURE_REFERENCE_TIMESTAMP,
    create_human_evidence,
    create_human_requirement,
)
from app.agents.agent3_resources.interfaces import InMemoryResourceRepository
from app.agents.agent3_resources.schemas import (
    AgentMessageMetadata,
    AllocationRequest,
    HumanResourceRequirement,
    MessageType,
)
from app.agents.agent3_resources.service import ResourceAllocationService
from app.agents.agent4_orchestrator.advancement_engine import ProcessAdvancementEngine
from app.company_directory.schemas import ApprovalAuthorityRecord, CreateEmployeeInput, EmployeeRecord
from app.company_directory.seed import (
    AUTH_USER_FINANCE_MANAGER,
    AUTH_USER_REQUESTER,
    BPMFLOW_DEMO_TENANT_ID,
    DEPT_FINANCE,
    DEPT_PROCUREMENT,
    EMP_FINANCE_MANAGER,
    EMP_INACTIVE,
    EMP_PROCUREMENT_OFFICER_1,
    EMP_REQUESTER,
    RES_FINANCE_MANAGER,
    ROLE_PROCUREMENT_OFFICER,
    seed_bpmflow_demo_company,
)
from app.company_directory.service import reset_company_directory
from app.process_context.identity import clear_identity_links
from app.tests.test_process_context import TestAmountCurrencySurvive, TestNoInventedDefaults


def _meta(tenant_id=BPMFLOW_DEMO_TENANT_ID):
    return AgentMessageMetadata(
        correlation_id=uuid4(),
        process_instance_id=uuid4(),
        task_id=uuid4(),
        tenant_id=tenant_id,
        message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
    )


def _human_req(**overrides) -> HumanResourceRequirement:
    base = dict(
        requester_id=AUTH_USER_REQUESTER,
        task_deadline=FIXTURE_REFERENCE_TIMESTAMP + timedelta(days=14),
        estimated_effort_hours=Decimal("1"),
        process_stage="RESOURCE_PLANNING",
        process_id=uuid4(),
        process_context_ref=uuid4(),
        required_roles=["Procurement Officer"],
        requester_employee_id=EMP_REQUESTER,
    )
    base.update(overrides)
    return HumanResourceRequirement(**base)


@pytest.fixture
def directory_service():
    clear_identity_links()
    service = reset_company_directory()
    seed_bpmflow_demo_company(service)
    yield service
    reset_company_directory()
    clear_identity_links()


@pytest.fixture
def allocator(directory_service):
    return ResourceAllocationService(InMemoryResourceRepository(), directory=directory_service)


@pytest.mark.asyncio
async def test_procurement_officer_role_match(allocator) -> None:
    result = await allocator.process_allocation_request(
        AllocationRequest(metadata=_meta(), human_requirements=_human_req(), process_context_ref=uuid4()),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    eligible = result.human_requirement_result.eligible_candidates
    assert any(item.employee_id == EMP_PROCUREMENT_OFFICER_1 for item in eligible)
    assert any(item.employee_email == "procurement.officer@bpmflow-demo.example.com" for item in eligible)
    top = eligible[0]
    assert top.employee_id is not None
    assert top.resource_id is not None
    assert top.employee_id != top.resource_id
    assert top.eligibility == "ELIGIBLE"


@pytest.mark.asyncio
async def test_department_does_not_select_finance(allocator) -> None:
    result = await allocator.process_allocation_request(
        AllocationRequest(
            metadata=_meta(),
            human_requirements=_human_req(required_department_code="PROCUREMENT"),
            process_context_ref=uuid4(),
        ),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    ids = {item.employee_id for item in result.human_requirement_result.eligible_candidates}
    assert EMP_FINANCE_MANAGER not in ids
    assert EMP_PROCUREMENT_OFFICER_1 in ids


@pytest.mark.asyncio
async def test_required_skills_are_checked(allocator) -> None:
    result = await allocator.process_allocation_request(
        AllocationRequest(
            metadata=_meta(),
            human_requirements=_human_req(mandatory_skills=["procurement"]),
            process_context_ref=uuid4(),
        ),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    assert result.human_requirement_result.eligible_candidates
    assert any(
        any(reason.reason == ExclusionReason.MANDATORY_SKILL_MISSING for reason in item.exclusion_reasons)
        for item in result.human_requirement_result.excluded_resources
    )


@pytest.mark.asyncio
async def test_insufficient_authority_is_hard_exclusion(directory_service) -> None:
    finance_role = directory_service.resolve_employee_by_employee_id(
        tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
    ).role_id
    low_limit = directory_service.create_employee(
        CreateEmployeeInput(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            employee_number="EMP-LIMIT",
            full_name="Limited Approver",
            email="limited.approver@bpmflow-demo.example.com",
            department_id=DEPT_FINANCE,
            role_id=finance_role,
        )
    )
    directory_service.create_authority(
        ApprovalAuthorityRecord(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            employee_id=low_limit.employee_id,
            approval_type="FINANCE",
            authority_code="FINANCE_APPROVAL",
            max_amount=Decimal("500000"),
            currency="LKR",
        )
    )
    allocator = ResourceAllocationService(InMemoryResourceRepository(), directory=directory_service)
    result = await allocator.process_allocation_request(
        AllocationRequest(
            metadata=_meta(),
            human_requirements=_human_req(
                required_roles=["Finance Manager"],
                minimum_authority_amount=Decimal("1500000"),
                authority_currency="LKR",
                required_authority_code="FINANCE_APPROVAL",
            ),
            process_context_ref=uuid4(),
        ),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    excluded_ids = {item.employee_id for item in result.human_requirement_result.excluded_resources}
    eligible_ids = {item.employee_id for item in result.human_requirement_result.eligible_candidates}
    assert low_limit.employee_id in excluded_ids
    assert EMP_FINANCE_MANAGER in eligible_ids


@pytest.mark.asyncio
async def test_unavailable_employee_rejected(directory_service) -> None:
    officer = directory_service.resolve_employee_by_employee_id(
        tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_PROCUREMENT_OFFICER_1
    )
    directory_service.create_employee(
        CreateEmployeeInput(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            employee_id=officer.employee_id,
            employee_number=officer.employee_number,
            full_name=officer.full_name,
            email=officer.email,
            department_id=officer.department_id,
            role_id=officer.role_id,
            manager_employee_id=officer.manager_employee_id,
            resource_id=officer.resource_id,
            skill_codes=officer.skill_codes,
            is_available=False,
            current_workload_pct=officer.current_workload_pct,
            max_workload_pct=officer.max_workload_pct,
        )
    )
    allocator = ResourceAllocationService(InMemoryResourceRepository(), directory=directory_service)
    result = await allocator.process_allocation_request(
        AllocationRequest(
            metadata=_meta(),
            human_requirements=_human_req(),
            process_context_ref=uuid4(),
        ),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    eligible_ids = {item.employee_id for item in result.human_requirement_result.eligible_candidates}
    assert EMP_PROCUREMENT_OFFICER_1 not in eligible_ids


@pytest.mark.asyncio
async def test_workload_ranks_after_eligibility(directory_service) -> None:
    busy = directory_service.create_employee(
        CreateEmployeeInput(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            employee_number="EMP-BUSY",
            full_name="Busy Officer",
            email="busy.officer@bpmflow-demo.example.com",
            department_id=DEPT_PROCUREMENT,
            role_id=ROLE_PROCUREMENT_OFFICER,
            skill_codes=["procurement"],
            current_workload_pct=Decimal("80"),
            max_workload_pct=Decimal("100"),
        )
    )
    light = directory_service.create_employee(
        CreateEmployeeInput(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            employee_number="EMP-LIGHT",
            full_name="Light Officer",
            email="light.officer@bpmflow-demo.example.com",
            department_id=DEPT_PROCUREMENT,
            role_id=ROLE_PROCUREMENT_OFFICER,
            skill_codes=["procurement"],
            current_workload_pct=Decimal("5"),
            max_workload_pct=Decimal("100"),
        )
    )
    allocator = ResourceAllocationService(InMemoryResourceRepository(), directory=directory_service)
    result = await allocator.process_allocation_request(
        AllocationRequest(metadata=_meta(), human_requirements=_human_req(), process_context_ref=uuid4()),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    eligible = {item.employee_id: item for item in result.human_requirement_result.eligible_candidates}
    assert eligible[light.employee_id].rank < eligible[busy.employee_id].rank


@pytest.mark.asyncio
async def test_inactive_employee_excluded(allocator) -> None:
    result = await allocator.process_allocation_request(
        AllocationRequest(
            metadata=_meta(),
            human_requirements=_human_req(required_roles=["Finance Manager"]),
            process_context_ref=uuid4(),
        ),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    eligible_ids = {item.employee_id for item in result.human_requirement_result.eligible_candidates}
    assert EMP_INACTIVE not in eligible_ids
    assert EMP_FINANCE_MANAGER in eligible_ids


@pytest.mark.asyncio
async def test_identity_mapping_auth_employee_resource(directory_service) -> None:
    employee = directory_service.resolve_employee_by_user_id(
        tenant_id=BPMFLOW_DEMO_TENANT_ID, user_id=AUTH_USER_FINANCE_MANAGER
    )
    assert employee is not None
    assert employee.employee_id == EMP_FINANCE_MANAGER
    assert employee.resource_id == RES_FINANCE_MANAGER
    assert len({employee.user_id, employee.employee_id, employee.resource_id}) == 3


@pytest.mark.asyncio
async def test_email_comes_from_directory(allocator) -> None:
    result = await allocator.process_allocation_request(
        AllocationRequest(metadata=_meta(), human_requirements=_human_req(), process_context_ref=uuid4()),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    for item in result.human_requirement_result.eligible_candidates:
        assert item.employee_email.endswith("@bpmflow-demo.example.com")
        assert "gmail.com" not in item.employee_email


@pytest.mark.asyncio
async def test_missing_email_is_not_invented(directory_service) -> None:
    officer = directory_service.resolve_employee_by_employee_id(
        tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_PROCUREMENT_OFFICER_1
    )
    directory_service.repository._employees[(BPMFLOW_DEMO_TENANT_ID, officer.employee_id)] = (
        EmployeeRecord.model_construct(**{**officer.model_dump(), "email": ""})
    )
    allocator = ResourceAllocationService(InMemoryResourceRepository(), directory=directory_service)
    result = await allocator.process_allocation_request(
        AllocationRequest(metadata=_meta(), human_requirements=_human_req(), process_context_ref=uuid4()),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    excluded = [
        item
        for item in result.human_requirement_result.excluded_resources
        if item.employee_id == EMP_PROCUREMENT_OFFICER_1
    ]
    assert excluded
    assert any(reason.reason == ExclusionReason.MISSING_COMPANY_EMAIL for reason in excluded[0].exclusion_reasons)


@pytest.mark.asyncio
async def test_sod_same_person_and_missing_approver(allocator) -> None:
    same = await allocator.process_allocation_request(
        AllocationRequest(
            metadata=_meta(),
            human_requirements=_human_req(
                assignment_kind="approver",
                required_approval_type="FINANCE",
                required_roles=["Finance Manager"],
                requester_employee_id=EMP_FINANCE_MANAGER,
                requester_id=AUTH_USER_FINANCE_MANAGER,
            ),
            process_context_ref=uuid4(),
        ),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    assert same.error_code == FailureErrorCode.APPROVER_NOT_RESOLVED.value
    missing = await allocator.process_allocation_request(
        AllocationRequest(
            metadata=_meta(),
            human_requirements=_human_req(
                assignment_kind="approver",
                required_approval_type="DOES_NOT_EXIST",
                required_roles=["Finance Manager"],
            ),
            process_context_ref=uuid4(),
        ),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    assert missing.error_code == FailureErrorCode.APPROVER_NOT_RESOLVED.value


@pytest.mark.asyncio
async def test_cross_tenant_isolation(directory_service, allocator) -> None:
    other = uuid4()
    result = await allocator.process_allocation_request(
        AllocationRequest(
            metadata=_meta(tenant_id=other),
            human_requirements=_human_req(),
            process_context_ref=uuid4(),
        ),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    assert result.human_requirement_result.eligible_candidates == []
    assert directory_service.resolve_email_for_employee(tenant_id=other, employee_id=EMP_FINANCE_MANAGER) is None


@pytest.mark.asyncio
async def test_no_eligible_resource_structured(allocator) -> None:
    result = await allocator.process_allocation_request(
        AllocationRequest(
            metadata=_meta(),
            human_requirements=_human_req(required_roles=["Moon Officer"]),
            process_context_ref=uuid4(),
        ),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    assert result.human_requirement_result.outcome_code == "NO_ELIGIBLE_RESOURCE"
    assert result.human_requirement_result.eligible_candidates == []


@pytest.mark.asyncio
async def test_identity_required_unmapped_fails(directory_service) -> None:
    allocator = ResourceAllocationService(InMemoryResourceRepository(), directory=directory_service)
    result = await allocator.process_allocation_request(
        AllocationRequest(
            metadata=_meta(),
            human_requirements=_human_req(
                requester_id=uuid4(),
                requester_employee_id=None,
                require_requester_identity=True,
            ),
            process_context_ref=uuid4(),
        ),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    assert result.error_code == FailureErrorCode.IDENTITY_NOT_RESOLVED.value


def test_agent4_production_path_has_no_synthetic_roles() -> None:
    source = getsource(ProcessAdvancementEngine._default_resource_planning)
    lowered = source.lower()
    assert '"developer"' not in lowered
    assert "'developer'" not in lowered
    assert '"python"' not in lowered
    assert '"fastapi"' not in lowered
    assert "acmeglobal" not in lowered


def test_phase1_amount_currency_unchanged() -> None:
    TestAmountCurrencySurvive().test_lkr_amount_survives_discovery_to_agent4_context()
    TestNoInventedDefaults().test_missing_amount_does_not_become_5000_usd()


def test_hard_authority_not_score_only() -> None:
    resource = create_human_evidence(
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
        roles=["Finance Manager"],
        authority="FINANCE_APPROVAL",
        reference_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    ).model_copy(update={"authority_max_amount": Decimal("500000"), "authority_currency": "LKR"})
    requirement = create_human_requirement(
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
        required_roles=["Finance Manager"],
        reference_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
        estimated_effort=Decimal("1"),
    ).model_copy(update={"minimum_authority_amount": Decimal("1500000"), "authority_currency": "LKR"})
    eligible, reasons = EligibilityEvaluator(FIXTURE_REFERENCE_TIMESTAMP).evaluate_eligibility(
        resource, requirement
    )
    assert eligible is False
    assert any(item.reason == ExclusionReason.INSUFFICIENT_AUTHORITY for item in reasons)
