"""Explicit BPMFlow Demo Company seed. Never runs automatically in production."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from .schemas import (
    ApprovalAuthorityRecord,
    BudgetDepartmentLink,
    CreateEmployeeInput,
    DepartmentRecord,
    RoleRecord,
)
from .service import CompanyDirectoryService, get_company_directory

BPMFLOW_DEMO_TENANT_ID = UUID("00000000-0000-0000-0000-00000000d001")
BPMFLOW_DEMO_TENANT_CODE = "BPMFLOW_DEMO"
BPMFLOW_DEMO_COMPANY_NAME = "BPMFlow Demo Company"
DEMO_EMAIL_DOMAIN = "bpmflow-demo.example.com"

# Departments
DEPT_MANAGEMENT = UUID("d0d00000-0000-4000-8000-000000000101")
DEPT_FINANCE = UUID("d0d00000-0000-4000-8000-000000000102")
DEPT_PROCUREMENT = UUID("d0d00000-0000-4000-8000-000000000103")
DEPT_IT = UUID("d0d00000-0000-4000-8000-000000000104")
DEPT_HR = UUID("d0d00000-0000-4000-8000-000000000105")
DEPT_OPERATIONS = UUID("d0d00000-0000-4000-8000-000000000106")

# Roles
ROLE_SENIOR_MANAGER = UUID("d0d00000-0000-4000-8000-000000000201")
ROLE_FINANCE_MANAGER = UUID("d0d00000-0000-4000-8000-000000000202")
ROLE_FINANCE_OFFICER = UUID("d0d00000-0000-4000-8000-000000000203")
ROLE_PROCUREMENT_MANAGER = UUID("d0d00000-0000-4000-8000-000000000204")
ROLE_PROCUREMENT_OFFICER = UUID("d0d00000-0000-4000-8000-000000000205")
ROLE_IT_MANAGER = UUID("d0d00000-0000-4000-8000-000000000206")
ROLE_IT_OFFICER = UUID("d0d00000-0000-4000-8000-000000000207")
ROLE_HR_MANAGER = UUID("d0d00000-0000-4000-8000-000000000208")
ROLE_HR_OFFICER = UUID("d0d00000-0000-4000-8000-000000000209")
ROLE_OPERATIONS = UUID("d0d00000-0000-4000-8000-000000000210")
ROLE_REQUESTER = UUID("d0d00000-0000-4000-8000-000000000211")

# Employees / resources (IDs intentionally distinct)
EMP_SENIOR_MANAGER = UUID("d0d00000-0000-4000-8000-000000000301")
EMP_FINANCE_MANAGER = UUID("d0d00000-0000-4000-8000-000000000302")
EMP_FINANCE_OFFICER = UUID("d0d00000-0000-4000-8000-000000000303")
EMP_PROCUREMENT_MANAGER = UUID("d0d00000-0000-4000-8000-000000000304")
EMP_PROCUREMENT_OFFICER_1 = UUID("d0d00000-0000-4000-8000-000000000305")
EMP_PROCUREMENT_OFFICER_2 = UUID("d0d00000-0000-4000-8000-000000000306")
EMP_IT_MANAGER = UUID("d0d00000-0000-4000-8000-000000000307")
EMP_IT_OFFICER_1 = UUID("d0d00000-0000-4000-8000-000000000308")
EMP_IT_OFFICER_2 = UUID("d0d00000-0000-4000-8000-000000000309")
EMP_IT_OFFICER_3 = UUID("d0d00000-0000-4000-8000-000000000310")
EMP_HR_MANAGER = UUID("d0d00000-0000-4000-8000-000000000311")
EMP_HR_OFFICER = UUID("d0d00000-0000-4000-8000-000000000312")
EMP_OPS_1 = UUID("d0d00000-0000-4000-8000-000000000313")
EMP_OPS_2 = UUID("d0d00000-0000-4000-8000-000000000314")
EMP_REQUESTER = UUID("d0d00000-0000-4000-8000-000000000315")
EMP_INACTIVE = UUID("d0d00000-0000-4000-8000-000000000316")
EMP_ANALYST = UUID("d0d00000-0000-4000-8000-000000000317")
EMP_COORDINATOR = UUID("d0d00000-0000-4000-8000-000000000318")

RES_SENIOR_MANAGER = UUID("d0d00000-0000-4000-8000-000000000401")
RES_FINANCE_MANAGER = UUID("d0d00000-0000-4000-8000-000000000402")
RES_FINANCE_OFFICER = UUID("d0d00000-0000-4000-8000-000000000403")
RES_PROCUREMENT_MANAGER = UUID("d0d00000-0000-4000-8000-000000000404")
RES_PROCUREMENT_OFFICER_1 = UUID("d0d00000-0000-4000-8000-000000000405")
RES_PROCUREMENT_OFFICER_2 = UUID("d0d00000-0000-4000-8000-000000000406")
RES_IT_MANAGER = UUID("d0d00000-0000-4000-8000-000000000407")
RES_IT_OFFICER_1 = UUID("d0d00000-0000-4000-8000-000000000408")
RES_IT_OFFICER_2 = UUID("d0d00000-0000-4000-8000-000000000409")
RES_IT_OFFICER_3 = UUID("d0d00000-0000-4000-8000-000000000410")
RES_HR_MANAGER = UUID("d0d00000-0000-4000-8000-000000000411")
RES_HR_OFFICER = UUID("d0d00000-0000-4000-8000-000000000412")
RES_OPS_1 = UUID("d0d00000-0000-4000-8000-000000000413")
RES_OPS_2 = UUID("d0d00000-0000-4000-8000-000000000414")
RES_REQUESTER = UUID("d0d00000-0000-4000-8000-000000000415")
RES_INACTIVE = UUID("d0d00000-0000-4000-8000-000000000416")
RES_ANALYST = UUID("d0d00000-0000-4000-8000-000000000417")
RES_COORDINATOR = UUID("d0d00000-0000-4000-8000-000000000418")
BUDGET_IT_2026 = UUID("d0d00000-0000-4000-8000-000000000501")

AUTH_USER_FINANCE_MANAGER = UUID("d0d00000-0000-4000-8000-000000000601")
AUTH_USER_REQUESTER = UUID("d0d00000-0000-4000-8000-000000000602")


def _email(local: str) -> str:
    return f"{local}@{DEMO_EMAIL_DOMAIN}"


def seed_bpmflow_demo_company(
    service: CompanyDirectoryService | None = None,
    *,
    tenant_id: UUID = BPMFLOW_DEMO_TENANT_ID,
) -> UUID:
    """Load fictional BPMFlow Demo Company data. Call explicitly — never auto-run."""
    directory = service or get_company_directory()

    departments = [
        ("MANAGEMENT", "Management", DEPT_MANAGEMENT),
        ("FINANCE", "Finance", DEPT_FINANCE),
        ("PROCUREMENT", "Procurement", DEPT_PROCUREMENT),
        ("IT", "IT", DEPT_IT),
        ("HR", "HR", DEPT_HR),
        ("OPERATIONS", "Operations", DEPT_OPERATIONS),
    ]
    for code, name, dept_id in departments:
        directory.create_department(
            DepartmentRecord(
                department_id=dept_id,
                tenant_id=tenant_id,
                name=name,
                code=code,
                status="active",
            )
        )

    roles = [
        (ROLE_SENIOR_MANAGER, "SENIOR_MANAGER", "Senior Manager", DEPT_MANAGEMENT),
        (ROLE_FINANCE_MANAGER, "FINANCE_MANAGER", "Finance Manager", DEPT_FINANCE),
        (ROLE_FINANCE_OFFICER, "FINANCE_OFFICER", "Finance Officer", DEPT_FINANCE),
        (ROLE_PROCUREMENT_MANAGER, "PROCUREMENT_MANAGER", "Procurement Manager", DEPT_PROCUREMENT),
        (ROLE_PROCUREMENT_OFFICER, "PROCUREMENT_OFFICER", "Procurement Officer", DEPT_PROCUREMENT),
        (ROLE_IT_MANAGER, "IT_MANAGER", "IT Manager", DEPT_IT),
        (ROLE_IT_OFFICER, "IT_OFFICER", "IT Officer", DEPT_IT),
        (ROLE_HR_MANAGER, "HR_MANAGER", "HR Manager", DEPT_HR),
        (ROLE_HR_OFFICER, "HR_OFFICER", "HR Officer", DEPT_HR),
        (ROLE_OPERATIONS, "OPERATIONS", "Operations Officer", DEPT_OPERATIONS),
        (ROLE_REQUESTER, "REQUESTER", "Requester", DEPT_IT),
    ]
    for role_id, code, name, dept_id in roles:
        directory.create_role(
            RoleRecord(
                role_id=role_id,
                tenant_id=tenant_id,
                code=code,
                name=name,
                description=f"{name} for {BPMFLOW_DEMO_COMPANY_NAME}",
                department_id=dept_id,
                status="active",
            )
        )

    people: list[dict] = [
        dict(
            employee_id=EMP_SENIOR_MANAGER,
            number="EMP-001",
            name="Amina Perera",
            email=_email("senior.manager"),
            dept=DEPT_MANAGEMENT,
            role=ROLE_SENIOR_MANAGER,
            manager=None,
            resource=RES_SENIOR_MANAGER,
            skills=["leadership", "governance"],
        ),
        dict(
            employee_id=EMP_FINANCE_MANAGER,
            number="EMP-010",
            name="Nimal Fernando",
            email=_email("finance.manager"),
            dept=DEPT_FINANCE,
            role=ROLE_FINANCE_MANAGER,
            manager=EMP_SENIOR_MANAGER,
            resource=RES_FINANCE_MANAGER,
            skills=["finance", "approval"],
            user_id=AUTH_USER_FINANCE_MANAGER,
        ),
        dict(
            employee_id=EMP_FINANCE_OFFICER,
            number="EMP-011",
            name="Ishara Jayawardena",
            email=_email("finance.officer"),
            dept=DEPT_FINANCE,
            role=ROLE_FINANCE_OFFICER,
            manager=EMP_FINANCE_MANAGER,
            resource=RES_FINANCE_OFFICER,
            skills=["finance", "reconciliation"],
        ),
        dict(
            employee_id=EMP_PROCUREMENT_MANAGER,
            number="EMP-020",
            name="Ruwan Silva",
            email=_email("procurement.manager"),
            dept=DEPT_PROCUREMENT,
            role=ROLE_PROCUREMENT_MANAGER,
            manager=EMP_SENIOR_MANAGER,
            resource=RES_PROCUREMENT_MANAGER,
            skills=["procurement", "vendor_management"],
        ),
        dict(
            employee_id=EMP_PROCUREMENT_OFFICER_1,
            number="EMP-021",
            name="Dilani Karunaratne",
            email=_email("procurement.officer"),
            dept=DEPT_PROCUREMENT,
            role=ROLE_PROCUREMENT_OFFICER,
            manager=EMP_PROCUREMENT_MANAGER,
            resource=RES_PROCUREMENT_OFFICER_1,
            skills=["procurement"],
        ),
        dict(
            employee_id=EMP_PROCUREMENT_OFFICER_2,
            number="EMP-022",
            name="Kasun Bandara",
            email=_email("procurement.officer2"),
            dept=DEPT_PROCUREMENT,
            role=ROLE_PROCUREMENT_OFFICER,
            manager=EMP_PROCUREMENT_MANAGER,
            resource=RES_PROCUREMENT_OFFICER_2,
            skills=["procurement"],
        ),
        dict(
            employee_id=EMP_IT_MANAGER,
            number="EMP-030",
            name="Thilini Wijesinghe",
            email=_email("it.manager"),
            dept=DEPT_IT,
            role=ROLE_IT_MANAGER,
            manager=EMP_SENIOR_MANAGER,
            resource=RES_IT_MANAGER,
            skills=["it", "infrastructure"],
        ),
        dict(
            employee_id=EMP_IT_OFFICER_1,
            number="EMP-031",
            name="Sahan Gunasekara",
            email=_email("it.officer1"),
            dept=DEPT_IT,
            role=ROLE_IT_OFFICER,
            manager=EMP_IT_MANAGER,
            resource=RES_IT_OFFICER_1,
            skills=["it"],
        ),
        dict(
            employee_id=EMP_IT_OFFICER_2,
            number="EMP-032",
            name="Malsha Abeysekera",
            email=_email("it.officer2"),
            dept=DEPT_IT,
            role=ROLE_IT_OFFICER,
            manager=EMP_IT_MANAGER,
            resource=RES_IT_OFFICER_2,
            skills=["it"],
        ),
        dict(
            employee_id=EMP_IT_OFFICER_3,
            number="EMP-033",
            name="Pradeep Rathnayake",
            email=_email("it.officer3"),
            dept=DEPT_IT,
            role=ROLE_IT_OFFICER,
            manager=EMP_IT_MANAGER,
            resource=RES_IT_OFFICER_3,
            skills=["it"],
        ),
        dict(
            employee_id=EMP_HR_MANAGER,
            number="EMP-040",
            name="Chathurika Mendis",
            email=_email("hr.manager"),
            dept=DEPT_HR,
            role=ROLE_HR_MANAGER,
            manager=EMP_SENIOR_MANAGER,
            resource=RES_HR_MANAGER,
            skills=["hr"],
        ),
        dict(
            employee_id=EMP_HR_OFFICER,
            number="EMP-041",
            name="Lakshan Dissanayake",
            email=_email("hr.officer"),
            dept=DEPT_HR,
            role=ROLE_HR_OFFICER,
            manager=EMP_HR_MANAGER,
            resource=RES_HR_OFFICER,
            skills=["hr"],
        ),
        dict(
            employee_id=EMP_OPS_1,
            number="EMP-050",
            name="Harsha Ekanayake",
            email=_email("operations.one"),
            dept=DEPT_OPERATIONS,
            role=ROLE_OPERATIONS,
            manager=EMP_SENIOR_MANAGER,
            resource=RES_OPS_1,
            skills=["operations"],
        ),
        dict(
            employee_id=EMP_OPS_2,
            number="EMP-051",
            name="Nadeesha Pathirana",
            email=_email("operations.two"),
            dept=DEPT_OPERATIONS,
            role=ROLE_OPERATIONS,
            manager=EMP_SENIOR_MANAGER,
            resource=RES_OPS_2,
            skills=["operations"],
        ),
        dict(
            employee_id=EMP_REQUESTER,
            number="EMP-060",
            name="Isuru Kodithuwakku",
            email=_email("it.requester"),
            dept=DEPT_IT,
            role=ROLE_REQUESTER,
            manager=EMP_IT_MANAGER,
            resource=RES_REQUESTER,
            skills=["it"],
            user_id=AUTH_USER_REQUESTER,
        ),
        dict(
            employee_id=EMP_INACTIVE,
            number="EMP-070",
            name="Former Approver",
            email=_email("former.approver"),
            dept=DEPT_FINANCE,
            role=ROLE_FINANCE_MANAGER,
            manager=EMP_SENIOR_MANAGER,
            resource=RES_INACTIVE,
            skills=["finance"],
            status="inactive",
        ),
        dict(
            employee_id=EMP_ANALYST,
            number="EMP-080",
            name="Sanduni Weerasinghe",
            email=_email("finance.analyst"),
            dept=DEPT_FINANCE,
            role=ROLE_FINANCE_OFFICER,
            manager=EMP_FINANCE_MANAGER,
            resource=RES_ANALYST,
            skills=["finance"],
        ),
        dict(
            employee_id=EMP_COORDINATOR,
            number="EMP-090",
            name="Janith Ranasinghe",
            email=_email("procurement.coordinator"),
            dept=DEPT_PROCUREMENT,
            role=ROLE_PROCUREMENT_OFFICER,
            manager=EMP_PROCUREMENT_MANAGER,
            resource=RES_COORDINATOR,
            skills=["procurement"],
        ),
    ]
    for person in people:
        directory.create_employee(
            CreateEmployeeInput(
                tenant_id=tenant_id,
                employee_id=person["employee_id"],
                employee_number=person["number"],
                full_name=person["name"],
                email=person["email"],
                department_id=person["dept"],
                role_id=person["role"],
                manager_employee_id=person["manager"],
                resource_id=person["resource"],
                user_id=person.get("user_id"),
                skill_codes=person["skills"],
                status=person.get("status", "active"),
                is_available=person.get("status", "active") == "active",
                current_workload_pct=Decimal("20"),
                max_workload_pct=Decimal("100"),
            )
        )

    directory.create_authority(
        ApprovalAuthorityRecord(
            tenant_id=tenant_id,
            employee_id=EMP_FINANCE_MANAGER,
            role_id=ROLE_FINANCE_MANAGER,
            approval_type="FINANCE",
            authority_code="FINANCE_APPROVAL",
            max_amount=Decimal("10000000"),
            currency="LKR",
            is_active=True,
        )
    )
    directory.create_authority(
        ApprovalAuthorityRecord(
            tenant_id=tenant_id,
            employee_id=EMP_SENIOR_MANAGER,
            role_id=ROLE_SENIOR_MANAGER,
            approval_type="SENIOR_MANAGEMENT",
            authority_code="SENIOR_MANAGEMENT_APPROVAL",
            max_amount=Decimal("50000000"),
            currency="LKR",
            is_active=True,
        )
    )
    directory.create_authority(
        ApprovalAuthorityRecord(
            tenant_id=tenant_id,
            employee_id=EMP_PROCUREMENT_MANAGER,
            role_id=ROLE_PROCUREMENT_MANAGER,
            approval_type="PROCUREMENT",
            authority_code="PROCUREMENT_APPROVAL",
            max_amount=Decimal("5000000"),
            currency="LKR",
            is_active=True,
        )
    )
    directory.create_authority(
        ApprovalAuthorityRecord(
            tenant_id=tenant_id,
            employee_id=EMP_INACTIVE,
            role_id=ROLE_FINANCE_MANAGER,
            approval_type="FINANCE",
            authority_code="FINANCE_APPROVAL",
            max_amount=Decimal("10000000"),
            currency="LKR",
            is_active=True,
        )
    )
    directory.link_budget_department(
        BudgetDepartmentLink(
            tenant_id=tenant_id,
            resource_id=BUDGET_IT_2026,
            department_id=DEPT_IT,
        )
    )
    return tenant_id
