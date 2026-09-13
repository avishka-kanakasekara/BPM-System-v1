"""Phase 2: company HR directory — tenant-scoped, no invented emails or IDs."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agents.agent3_resources import InMemoryResourceRepository, create_human_evidence
from app.company_directory.exceptions import ApproverNotResolvedError, InvalidManagerError
from app.company_directory.schemas import CreateEmployeeInput
from app.company_directory.seed import (
    AUTH_USER_FINANCE_MANAGER,
    AUTH_USER_REQUESTER,
    BPMFLOW_DEMO_TENANT_ID,
    EMP_FINANCE_MANAGER,
    EMP_INACTIVE,
    EMP_IT_OFFICER_1,
    EMP_PROCUREMENT_OFFICER_1,
    EMP_REQUESTER,
    EMP_SENIOR_MANAGER,
    RES_FINANCE_MANAGER,
    seed_bpmflow_demo_company,
)
from app.company_directory.service import CompanyDirectoryService, reset_company_directory
from app.main import app
from app.process_context.identity import clear_identity_links, resolve_employee_resource_id
from app.tests.auth_helpers import override_current_user
from app.tests.test_process_context import TestAmountCurrencySurvive, TestNoInventedDefaults


@pytest.fixture
def directory() -> CompanyDirectoryService:
    clear_identity_links()
    service = reset_company_directory()
    seed_bpmflow_demo_company(service)
    yield service
    reset_company_directory()
    clear_identity_links()


class TestCreateAndResolveEmployee:
    def test_create_employee(self, directory: CompanyDirectoryService) -> None:
        dept = directory.list_departments(tenant_id=BPMFLOW_DEMO_TENANT_ID)[0]
        role = next(
            item
            for item in directory.list_roles(tenant_id=BPMFLOW_DEMO_TENANT_ID)
            if item.name == "IT Officer"
        )
        created = directory.create_employee(
            CreateEmployeeInput(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                employee_number="EMP-199",
                full_name="New Hire",
                email="new.hire@bpmflow-demo.example.com",
                department_id=dept.department_id,
                role_id=role.role_id,
            )
        )
        assert created.employee_number == "EMP-199"
        assert created.email == "new.hire@bpmflow-demo.example.com"

    def test_resolve_by_employee_id(self, directory: CompanyDirectoryService) -> None:
        employee = directory.resolve_employee_by_employee_id(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
        )
        assert employee is not None
        assert employee.employee_number == "EMP-010"

    def test_resolve_by_auth_user_id(self, directory: CompanyDirectoryService) -> None:
        employee = directory.resolve_employee_by_user_id(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, user_id=AUTH_USER_FINANCE_MANAGER
        )
        assert employee is not None
        assert employee.employee_id == EMP_FINANCE_MANAGER
        assert employee.user_id != employee.employee_id
        assert employee.resource_id != employee.employee_id
        assert employee.user_id != employee.resource_id

    def test_resolve_resource(self, directory: CompanyDirectoryService) -> None:
        resource_id = directory.resolve_resource_for_employee(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
        )
        assert resource_id == RES_FINANCE_MANAGER

    def test_resolve_email(self, directory: CompanyDirectoryService) -> None:
        email = directory.resolve_email_for_employee(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
        )
        assert email == "finance.manager@bpmflow-demo.example.com"


class TestRoleResolution:
    def test_resolve_finance_manager(self, directory: CompanyDirectoryService) -> None:
        matches = directory.resolve_employee_by_role(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, role_name="Finance Manager"
        )
        assert any(item.employee_id == EMP_FINANCE_MANAGER for item in matches)
        assert all(item.email.endswith("@bpmflow-demo.example.com") for item in matches)

    def test_resolve_senior_manager(self, directory: CompanyDirectoryService) -> None:
        matches = directory.resolve_employee_by_role(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, role_name="Senior Manager"
        )
        assert len(matches) == 1
        assert matches[0].employee_id == EMP_SENIOR_MANAGER
        assert matches[0].email == "senior.manager@bpmflow-demo.example.com"

    def test_resolve_procurement_officer(self, directory: CompanyDirectoryService) -> None:
        matches = directory.resolve_employee_by_role(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, role_name="Procurement Officer"
        )
        assert any(item.employee_id == EMP_PROCUREMENT_OFFICER_1 for item in matches)
        assert len(matches) >= 2


class TestHierarchyAndAuthority:
    def test_resolve_manager_relationship(self, directory: CompanyDirectoryService) -> None:
        manager = directory.resolve_manager(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
        )
        assert manager is not None
        assert manager.employee_id == EMP_SENIOR_MANAGER

    def test_self_manager_rejected(self, directory: CompanyDirectoryService) -> None:
        employee = directory.resolve_employee_by_employee_id(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_IT_OFFICER_1
        )
        assert employee is not None
        with pytest.raises(InvalidManagerError):
            directory.create_employee(
                CreateEmployeeInput(
                    tenant_id=BPMFLOW_DEMO_TENANT_ID,
                    employee_id=employee.employee_id,
                    employee_number="EMP-SELF",
                    full_name="Loop",
                    email="loop@bpmflow-demo.example.com",
                    department_id=employee.department_id,
                    role_id=employee.role_id,
                    manager_employee_id=employee.employee_id,
                )
            )

    def test_resolve_approval_authority(self, directory: CompanyDirectoryService) -> None:
        authorities = directory.resolve_approval_authority(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            employee_id=EMP_FINANCE_MANAGER,
            approval_type="FINANCE",
        )
        assert authorities
        assert authorities[0].authority_code == "FINANCE_APPROVAL"

    def test_verify_approval_limit(self, directory: CompanyDirectoryService) -> None:
        authorities = directory.resolve_approval_authority(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            employee_id=EMP_FINANCE_MANAGER,
            approval_type="FINANCE",
        )
        assert authorities[0].max_amount == Decimal("10000000")
        assert authorities[0].currency == "LKR"
        candidates = directory.resolve_active_approvers(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            approval_type="FINANCE",
            amount=Decimal("2500000"),
            currency="LKR",
            required_authority="FINANCE_APPROVAL",
        )
        assert any(item.employee_id == EMP_FINANCE_MANAGER for item in candidates)
        assert all(item.email.endswith("@bpmflow-demo.example.com") for item in candidates)


class TestSegregationOfDuties:
    def test_same_employee_detected(self, directory: CompanyDirectoryService) -> None:
        result = directory.compare_requester_approver(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            requester_employee_id=EMP_REQUESTER,
            approver_employee_id=EMP_REQUESTER,
        )
        assert result.status == "SAME_PERSON"
        assert result.same_person is True

    def test_unknown_approver_not_resolved(self, directory: CompanyDirectoryService) -> None:
        result = directory.compare_requester_approver(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            requester_employee_id=EMP_REQUESTER,
            approver_employee_id=None,
        )
        assert result.status == "APPROVER_NOT_RESOLVED"
        with pytest.raises(ApproverNotResolvedError) as exc:
            directory.compare_requester_approver(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                requester_employee_id=EMP_REQUESTER,
                approver_employee_id=uuid4(),
            )
        assert exc.value.error_code == "APPROVER_NOT_RESOLVED"


class TestNoInvention:
    def test_unknown_email_is_not_generated(self, directory: CompanyDirectoryService) -> None:
        email = directory.resolve_email_for_employee(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=uuid4()
        )
        assert email is None

    def test_cross_tenant_lookup_blocked(self, directory: CompanyDirectoryService) -> None:
        other = uuid4()
        assert (
            directory.resolve_employee_by_employee_id(
                tenant_id=other, employee_id=EMP_FINANCE_MANAGER
            )
            is None
        )
        with pytest.raises(Exception):
            directory.require_tenant_match(tenant_id=BPMFLOW_DEMO_TENANT_ID, other_tenant_id=other)

    def test_inactive_not_active_approver(self, directory: CompanyDirectoryService) -> None:
        candidates = directory.resolve_active_approvers(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            approval_type="FINANCE",
            currency="LKR",
        )
        ids = {item.employee_id for item in candidates}
        assert EMP_FINANCE_MANAGER in ids
        assert EMP_INACTIVE not in ids


class TestAgent3ResourceLink:
    def test_resource_stays_linked(self, directory: CompanyDirectoryService) -> None:
        resource_id = directory.resolve_resource_for_employee(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
        )
        assert resource_id == RES_FINANCE_MANAGER
        repo = InMemoryResourceRepository()
        repo.add_human_resource(
            create_human_evidence(
                tenant_id=BPMFLOW_DEMO_TENANT_ID,
                resource_id=RES_FINANCE_MANAGER,
                name="Nimal Fernando",
                roles=["FINANCE_MANAGER"],
            )
        )
        humans = [
            item
            for item in repo._human_resources
            if item.tenant_id == BPMFLOW_DEMO_TENANT_ID
        ]
        assert any(item.resource_id == RES_FINANCE_MANAGER for item in humans)
        employee = directory.resolve_employee_by_employee_id(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, employee_id=EMP_FINANCE_MANAGER
        )
        assert employee is not None
        assert employee.resource_id == humans[0].resource_id or employee.resource_id == RES_FINANCE_MANAGER

    def test_identity_link_maps_user_to_resource(self, directory: CompanyDirectoryService) -> None:
        resource_id = resolve_employee_resource_id(
            user_id=AUTH_USER_FINANCE_MANAGER, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        assert resource_id == RES_FINANCE_MANAGER
        requester = directory.resolve_employee_by_user_id(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, user_id=AUTH_USER_REQUESTER
        )
        assert requester is not None
        assert requester.employee_id == EMP_REQUESTER


class TestCompanyApi:
    def test_list_employees_is_tenant_scoped(self, directory: CompanyDirectoryService) -> None:
        override_current_user(role="requester", tenant_id=BPMFLOW_DEMO_TENANT_ID)
        client = TestClient(app)
        response = client.get("/api/v1/company/employees")
        assert response.status_code == 200
        body = response.json()
        assert any(row["employee_number"] == "EMP-010" for row in body)
        app.dependency_overrides.clear()

    def test_approvers_endpoint(self, directory: CompanyDirectoryService) -> None:
        override_current_user(role="approver", tenant_id=BPMFLOW_DEMO_TENANT_ID)
        client = TestClient(app)
        response = client.get(
            "/api/v1/company/approvers",
            params={
                "approval_type": "FINANCE",
                "amount": "2500000",
                "currency": "LKR",
                "required_authority": "FINANCE_APPROVAL",
            },
        )
        assert response.status_code == 200
        emails = {row["email"] for row in response.json()}
        assert "finance.manager@bpmflow-demo.example.com" in emails
        assert "finance.manager@gmail.com" not in emails
        app.dependency_overrides.clear()

    def test_foreign_tenant_sees_empty_directory(self, directory: CompanyDirectoryService) -> None:
        override_current_user(role="admin", tenant_id=uuid4())
        client = TestClient(app)
        response = client.get("/api/v1/company/employees")
        assert response.status_code == 200
        assert response.json() == []
        app.dependency_overrides.clear()


class TestPhase1StillHolds:
    def test_amount_currency_survive(self) -> None:
        TestAmountCurrencySurvive().test_lkr_amount_survives_discovery_to_agent4_context()

    def test_missing_amount_not_invented(self) -> None:
        TestNoInventedDefaults().test_missing_amount_does_not_become_5000_usd()
