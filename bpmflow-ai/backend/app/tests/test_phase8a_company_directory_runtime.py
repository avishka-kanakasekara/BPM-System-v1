"""Phase 8A: DB-backed Company Directory runtime and Agent 2 recipient resolution."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.agents.agent2_execution.security.tool_guard import ToolGuard
from app.agents.agent2_execution.workflow_step.exceptions import ConflictingExecutionInputError
from app.agents.agent2_execution.workflow_step.inputs import (
    build_tool_parameters,
    reject_conflicting_overrides,
)
from app.agents.agent3_resources.interfaces import InMemoryResourceRepository
from app.agents.agent3_resources.service import ResourceAllocationService
from app.agents.agent4_orchestrator.constants import WorkflowStage
from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository
from app.agents.agent4_orchestrator.workflow_plan.constants import WorkflowPlanStatus
from app.agents.agent4_orchestrator.workflow_plan.planner import WorkflowPlanner
from app.agents.agent4_orchestrator.workflow_plan.repository import InMemoryWorkflowPlanRepository
from app.agents.agent4_orchestrator.workflow_plan.service import WorkflowPlanService
from app.company_directory.db_repository import SqlAlchemyCompanyDirectoryRepository
from app.company_directory.exceptions import (
    CommunicationRecipientInvalidError,
    CompanyDirectoryUnavailableError,
    CrossTenantDirectoryError,
    EmployeeNotFoundError,
    MissingCompanyEmailError,
)
from app.company_directory.repository import InMemoryCompanyDirectoryRepository
from app.company_directory.schemas import CreateEmployeeInput, EmployeeRecord
from app.company_directory.seed import (
    AUTH_USER_FINANCE_MANAGER,
    AUTH_USER_REQUESTER,
    BPMFLOW_DEMO_TENANT_ID,
    DEPT_FINANCE,
    EMP_FINANCE_MANAGER,
    EMP_INACTIVE,
    EMP_PROCUREMENT_OFFICER_1,
    EMP_REQUESTER,
    EMP_SENIOR_MANAGER,
    RES_FINANCE_MANAGER,
    ROLE_FINANCE_MANAGER,
    seed_bpmflow_demo_company,
)
from app.company_directory.service import (
    CompanyDirectoryService,
    get_company_directory,
    reset_company_directory,
)
from app.core.persistence.policy import PersistenceMode
from app.policy_knowledge import PolicyIngestionService, PolicyRetrievalService
from app.policy_knowledge.repository import InMemoryPolicyRepository
from app.process_context.schemas import ProcessContext
from app.tests.test_workflow_planning import _ctx, _seed_policy
from app.tool_registry.repository import InMemoryToolRegistryRepository
from app.tool_registry.seed import seed_bpmflow_tool_registry
from app.tool_registry.service import ToolRegistryService

OTHER_TENANT = UUID("00000000-0000-0000-0000-00000000d099")
ORG_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "agents"
    / "agent2_execution"
    / "data"
    / "org_directory.json"
)


def _sqlite_directory() -> CompanyDirectoryService:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE departments (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    code TEXT NOT NULL,
                    manager_employee_id TEXT,
                    status TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE roles (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    department_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    UNIQUE (tenant_id, code)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE employees (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    employee_number TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    phone TEXT,
                    department_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    manager_employee_id TEXT,
                    status TEXT NOT NULL,
                    resource_id TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE approval_authorities (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    employee_id TEXT,
                    role_id TEXT,
                    department_id TEXT,
                    approval_type TEXT NOT NULL,
                    authority_code TEXT,
                    max_amount NUMERIC NOT NULL,
                    currency TEXT NOT NULL,
                    is_active INTEGER NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE identity_links (
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    employee_id TEXT,
                    resource_id TEXT,
                    employee_resource_id TEXT,
                    PRIMARY KEY (tenant_id, user_id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE skills (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    UNIQUE (tenant_id, code)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE resource_skills (
                    tenant_id TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    proficiency NUMERIC,
                    PRIMARY KEY (tenant_id, resource_id, skill_id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE resource_availability (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    available_from TEXT NOT NULL,
                    available_until TEXT,
                    reason TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE workload_snapshots (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    snapshot_at TEXT NOT NULL,
                    current_workload_pct NUMERIC NOT NULL,
                    max_workload_pct NUMERIC NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE TABLE budget_resource_profiles (tenant_id TEXT, resource_id TEXT, department_id TEXT)"))
    factory = sessionmaker(bind=engine)
    return CompanyDirectoryService(SqlAlchemyCompanyDirectoryRepository(factory))


@pytest.fixture
def db_directory() -> CompanyDirectoryService:
    service = _sqlite_directory()
    seed_bpmflow_demo_company(service)
    return service


class TestDatabaseDirectoryLookups:
    def test_employee_resource_role_department_manager_authority_skill(self, db_directory):
        employee = db_directory.resolve_employee_by_employee_id(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
        )
        assert employee is not None
        assert employee.employee_number == "EMP-010"
        assert employee.resource_id == RES_FINANCE_MANAGER
        role = db_directory.get_role(tenant_id=BPMFLOW_DEMO_TENANT_ID, role_id=employee.role_id)
        dept = db_directory.get_department(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, department_id=employee.department_id
        )
        assert role is not None and role.name == "Finance Manager"
        assert dept is not None and dept.code == "FINANCE"
        manager = db_directory.resolve_manager(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
        )
        assert manager is not None and manager.employee_id == EMP_SENIOR_MANAGER
        authorities = db_directory.resolve_approval_authority(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            employee_id=EMP_FINANCE_MANAGER,
            approval_type="FINANCE",
        )
        assert authorities and authorities[0].authority_code == "FINANCE_APPROVAL"
        assert "finance" in {code.lower() for code in employee.skill_codes}

    def test_identity_chain(self, db_directory):
        employee = db_directory.resolve_employee_by_user_id(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, user_id=AUTH_USER_FINANCE_MANAGER
        )
        assert employee is not None
        assert employee.employee_id == EMP_FINANCE_MANAGER
        assert db_directory.resolve_resource_for_employee(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
        ) == RES_FINANCE_MANAGER
        assert db_directory.resolve_user_for_employee(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
        ) == AUTH_USER_FINANCE_MANAGER
        assert db_directory.require_email_for_employee(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
        ) == "finance.manager@bpmflow-demo.example.com"

    def test_missing_employee_and_email(self, db_directory):
        with pytest.raises(EmployeeNotFoundError):
            db_directory.require_email_for_employee(tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=uuid4())
        session = db_directory.repository._session_factory()
        session.execute(text("UPDATE employees SET email = '' WHERE id = :id"), {"id": str(EMP_FINANCE_MANAGER)})
        session.commit()
        session.close()
        with pytest.raises(MissingCompanyEmailError):
            db_directory.require_email_for_employee(
                tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
            )

    def test_cross_tenant_lookups_are_empty(self, db_directory):
        assert (
            db_directory.resolve_employee_by_employee_id(
                tenant_id=OTHER_TENANT, employee_id=EMP_FINANCE_MANAGER
            )
            is None
        )
        assert db_directory.resolve_resource_for_employee(
            tenant_id=OTHER_TENANT, employee_id=EMP_FINANCE_MANAGER
        ) is None
        assert db_directory.resolve_approval_authority(
            tenant_id=OTHER_TENANT, employee_id=EMP_FINANCE_MANAGER, approval_type="FINANCE"
        ) == []
        with pytest.raises(CrossTenantDirectoryError):
            db_directory.require_tenant_match(
                tenant_id=BPMFLOW_DEMO_TENANT_ID, other_tenant_id=OTHER_TENANT
            )


class TestUnavailableDirectory:
    def test_no_demo_fallback_when_db_unavailable(self, monkeypatch):
        import app.company_directory.service as service_mod

        service_mod._DEFAULT_SERVICE = None
        service_mod._DEFAULT_REPO = None
        monkeypatch.setattr(service_mod, "_open_runtime_repository", lambda: (_ for _ in ()).throw(
            CompanyDirectoryUnavailableError("Company directory database is unavailable")
        ))
        with pytest.raises(CompanyDirectoryUnavailableError) as exc:
            get_company_directory()
        assert exc.value.error_code == "COMPANY_DIRECTORY_UNAVAILABLE"
        reset_company_directory()


@pytest.mark.asyncio
async def test_agent3_allocation_uses_directory_people(db_directory):
    from datetime import timedelta

    from app.agents.agent3_resources.constants import MessageType
    from app.agents.agent3_resources.fixtures import FIXTURE_REFERENCE_TIMESTAMP
    from app.agents.agent3_resources.schemas import (
        AgentMessageMetadata,
        AllocationRequest,
        HumanResourceRequirement,
    )

    allocator = ResourceAllocationService(InMemoryResourceRepository(), directory=db_directory)
    result = await allocator.process_allocation_request(
        AllocationRequest(
            metadata=AgentMessageMetadata(
                correlation_id=uuid4(),
                process_instance_id=uuid4(),
                task_id=uuid4(),
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            ),
            human_requirements=HumanResourceRequirement(
                requester_id=AUTH_USER_REQUESTER,
                task_deadline=FIXTURE_REFERENCE_TIMESTAMP + timedelta(days=14),
                estimated_effort_hours=Decimal("1"),
                process_stage="RESOURCE_PLANNING",
                process_id=uuid4(),
                required_roles=["Procurement Officer"],
                requester_employee_id=EMP_REQUESTER,
            ),
            process_context_ref=uuid4(),
        ),
        evaluation_timestamp=FIXTURE_REFERENCE_TIMESTAMP,
    )
    eligible = result.human_requirement_result.eligible_candidates
    assert any(item.employee_id == EMP_PROCUREMENT_OFFICER_1 for item in eligible)


class TestAgent2CommunicationResolution:
    def test_resolves_employee_id_to_email(self, db_directory):
        from app.agents.agent4_orchestrator.workflow_plan.constants import WorkflowStepType
        from app.agents.agent4_orchestrator.workflow_plan.schemas import WorkflowStepRecord
        from datetime import UTC, datetime

        step = WorkflowStepRecord(
            id=uuid4(),
            workflow_plan_id=uuid4(),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            step_key="notify-finance",
            sequence=1,
            name="Notify finance",
            step_type=WorkflowStepType.COMMUNICATION,
            required_action="SEND_EMAIL",
            recipient_employee_ids=[EMP_FINANCE_MANAGER],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        ctx = _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2)
        params = build_tool_parameters(
            context=ctx,
            step=step,
            process_id=ctx.process_id,
            task_id=str(step.id),
            directory=db_directory,
        )
        assert params["recipient"] == "finance.manager@bpmflow-demo.example.com"
        assert params["directory_verified"] is True

    def test_rejects_raw_email_override(self, db_directory):
        ctx = _ctx(uuid4(), amount="1500000", budget="2000000", quotes=2)
        with pytest.raises(ConflictingExecutionInputError):
            reject_conflicting_overrides(
                context=ctx,
                caller_parameters={"recipient": "someone@example.com"},
            )

    def test_rejects_missing_and_inactive(self, db_directory):
        with pytest.raises(MissingCompanyEmailError):
            employee = db_directory.resolve_employee_by_employee_id(
                tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
            )
            assert employee is not None
            session = db_directory.repository._session_factory()
            session.execute(
                text("UPDATE employees SET email = '' WHERE id = :id"),
                {"id": str(EMP_FINANCE_MANAGER)},
            )
            session.commit()
            session.close()
            db_directory.require_email_for_employee(
                tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
            )
        with pytest.raises(CommunicationRecipientInvalidError):
            db_directory.require_email_for_employee(
                tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_INACTIVE
            )

    def test_multiple_recipients_fail_closed(self, db_directory):
        from app.company_directory.communication import resolve_verified_recipient_emails

        with pytest.raises(EmployeeNotFoundError):
            resolve_verified_recipient_emails(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                employee_ids=[EMP_FINANCE_MANAGER, uuid4()],
                directory=db_directory,
            )

    def test_org_directory_json_not_used_by_tool_guard(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "agents"
            / "agent2_execution"
            / "security"
            / "tool_guard.py"
        ).read_text(encoding="utf-8")
        assert "org_directory.json" not in source
        assert ORG_DIRECTORY.exists()


@pytest.mark.asyncio
async def test_end_to_end_directory_plan_and_email_resolution(db_directory):
    processes = InMemoryProcessRepository()
    plans = WorkflowPlanService(InMemoryWorkflowPlanRepository(), directory=db_directory)
    tools = ToolRegistryService(InMemoryToolRegistryRepository())
    await seed_bpmflow_tool_registry(tools, tenant_id=BPMFLOW_DEMO_TENANT_ID)
    policy_repo = InMemoryPolicyRepository()
    await _seed_policy(PolicyIngestionService(policy_repo), BPMFLOW_DEMO_TENANT_ID)
    planner = WorkflowPlanner(
        plan_service=plans,
        process_repository=processes,
        policy_retrieval=PolicyRetrievalService(policy_repo),
        tool_registry=tools,
        directory=db_directory,
        allocator=ResourceAllocationService(InMemoryResourceRepository(), directory=db_directory),
    )
    record = await processes.insert_process(
        name="PR-2026-0098",
        process_type="procurement",
        description="laptop refresh",
        created_by=AUTH_USER_REQUESTER,
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
    )
    ctx = _ctx(record.id, amount="1500000", budget="2000000", quotes=2)
    processes._records[record.id] = record.model_copy(
        update={"process_context": ctx.model_dump(mode="json")}
    )
    result = await planner.generate_plan(process_id=record.id, tenant_id=BPMFLOW_DEMO_TENANT_ID)
    by_key = {step.step_key: step for step in result.steps}
    assert by_key["review-purchase-request"].responsible_employee_id == EMP_PROCUREMENT_OFFICER_1
    assert by_key["finance-approval"].responsible_employee_id == EMP_FINANCE_MANAGER
    assert by_key["senior-management-approval"].responsible_employee_id == EMP_SENIOR_MANAGER
    comm = next(
        step
        for step in result.steps
        if step.recipient_employee_ids
    )
    params = build_tool_parameters(
        context=ctx,
        step=comm,
        process_id=record.id,
        task_id=str(comm.id),
        directory=db_directory,
    )
    assert "@bpmflow-demo.example.com" in params["recipient"]
    assert "org_directory" not in str(params)
    guard = ToolGuard(session=None, directory=db_directory)
    guard_result = await guard.check(
        "send_email",
        {
            **params,
            "subject": "Notice",
            "body": "Body",
        },
        actor="agent_2",
    )
    assert guard_result.allowed is True
