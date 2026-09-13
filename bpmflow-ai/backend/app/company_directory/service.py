"""Tenant-scoped CompanyDirectoryService. Agents consume this, not raw tables."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.core.logging import get_logger

from .exceptions import (
    ApproverNotResolvedError,
    CommunicationRecipientInvalidError,
    CompanyDirectoryUnavailableError,
    CrossTenantDirectoryError,
    EmployeeNotFoundError,
    MissingCompanyEmailError,
)
from .repository import CompanyDirectoryRepository, InMemoryCompanyDirectoryRepository
from .schemas import (
    ApprovalAuthorityRecord,
    ApproverCandidate,
    BudgetDepartmentLink,
    CreateEmployeeInput,
    DepartmentRecord,
    EmployeeRecord,
    IdentityMapping,
    RoleRecord,
    SodComparison,
)

_DEFAULT_REPO: CompanyDirectoryRepository | None = None
_DEFAULT_SERVICE: CompanyDirectoryService | None = None
_USING_TEST_DIRECTORY = False
logger = get_logger(__name__)


class CompanyDirectoryService:
    """Authoritative company HR lookups. Never invents email, employee, or approver."""

    def __init__(self, repository: CompanyDirectoryRepository) -> None:
        self._repo = repository

    @property
    def repository(self) -> CompanyDirectoryRepository:
        return self._repo

    def create_department(self, department: DepartmentRecord) -> DepartmentRecord:
        return self._repo.create_department(department)

    def create_role(self, role: RoleRecord) -> RoleRecord:
        return self._repo.create_role(role)

    def create_employee(self, payload: CreateEmployeeInput) -> EmployeeRecord:
        record = self._repo.create_employee(payload)
        self._sync_process_context_identity(record)
        return record

    def create_authority(self, authority: ApprovalAuthorityRecord) -> ApprovalAuthorityRecord:
        return self._repo.create_authority(authority)

    def link_identity(self, mapping: IdentityMapping) -> IdentityMapping:
        stored = self._repo.link_identity(mapping)
        employee = None
        if stored.employee_id is not None:
            employee = self._repo.get_employee(tenant_id=stored.tenant_id, employee_id=stored.employee_id)
        if employee is not None:
            self._sync_process_context_identity(employee)
        return stored

    def link_budget_department(self, link: BudgetDepartmentLink) -> BudgetDepartmentLink:
        return self._repo.link_budget_department(link)

    def resolve_employee_by_employee_id(
        self, *, tenant_id: UUID, employee_id: UUID
    ) -> EmployeeRecord | None:
        return self._repo.get_employee(tenant_id=tenant_id, employee_id=employee_id)

    def resolve_employee_by_user_id(self, *, tenant_id: UUID, user_id: UUID) -> EmployeeRecord | None:
        mapping = self._repo.get_identity_by_user(tenant_id=tenant_id, user_id=user_id)
        if mapping is None or mapping.employee_id is None:
            return None
        return self._repo.get_employee(tenant_id=tenant_id, employee_id=mapping.employee_id)

    def resolve_resource_for_employee(
        self, *, tenant_id: UUID, employee_id: UUID
    ) -> UUID | None:
        employee = self._repo.get_employee(tenant_id=tenant_id, employee_id=employee_id)
        if employee is None:
            return None
        return employee.resource_id

    def resolve_user_for_employee(self, *, tenant_id: UUID, employee_id: UUID) -> UUID | None:
        mapping = self._repo.get_identity_by_employee(tenant_id=tenant_id, employee_id=employee_id)
        if mapping is not None:
            return mapping.auth_user_id
        employee = self._repo.get_employee(tenant_id=tenant_id, employee_id=employee_id)
        return None if employee is None else employee.user_id

    def resolve_email_for_employee(self, *, tenant_id: UUID, employee_id: UUID) -> str | None:
        employee = self._repo.get_employee(tenant_id=tenant_id, employee_id=employee_id)
        if employee is None:
            return None
        email = (employee.email or "").strip().lower()
        if not email or "@" not in email:
            return None
        return email

    def require_email_for_employee(self, *, tenant_id: UUID, employee_id: UUID) -> str:
        """Verified tenant-owned active employee email. Never invents an address."""
        try:
            employee = self._repo.get_employee(tenant_id=tenant_id, employee_id=employee_id)
        except CompanyDirectoryUnavailableError:
            raise
        except Exception as exc:
            raise CompanyDirectoryUnavailableError(
                "Company directory database is unavailable"
            ) from exc
        if employee is None:
            raise EmployeeNotFoundError("Employee not found in tenant company directory")
        if employee.tenant_id != tenant_id:
            raise CrossTenantDirectoryError("tenant A cannot resolve tenant B directory data")
        if employee.status != "active":
            raise CommunicationRecipientInvalidError(
                "Employee is not active",
                error_code="COMMUNICATION_RECIPIENT_INVALID",
            )
        email = (employee.email or "").strip().lower()
        if not email or "@" not in email:
            raise MissingCompanyEmailError("Employee is missing a verified company email")
        return email

    def resolve_employee_by_role(
        self,
        *,
        tenant_id: UUID,
        role_name: str | None = None,
        role_code: str | None = None,
        active_only: bool = True,
    ) -> list[EmployeeRecord]:
        needle_name = (role_name or "").strip().lower()
        needle_code = (role_code or "").strip().lower()
        matched_ids = {
            role.role_id
            for role in self._repo.list_roles(tenant_id=tenant_id)
            if (needle_name and role.name.lower() == needle_name)
            or (needle_code and role.code.lower() == needle_code)
        }
        results: list[EmployeeRecord] = []
        for employee in self._repo.list_employees(tenant_id=tenant_id):
            if employee.role_id not in matched_ids:
                continue
            if active_only and employee.status != "active":
                continue
            results.append(employee)
        return results

    def resolve_manager(self, *, tenant_id: UUID, employee_id: UUID) -> EmployeeRecord | None:
        employee = self._repo.get_employee(tenant_id=tenant_id, employee_id=employee_id)
        if employee is None or employee.manager_employee_id is None:
            return None
        return self._repo.get_employee(tenant_id=tenant_id, employee_id=employee.manager_employee_id)

    def list_employees(self, *, tenant_id: UUID) -> list[EmployeeRecord]:
        return self._repo.list_employees(tenant_id=tenant_id)

    def list_departments(self, *, tenant_id: UUID) -> list[DepartmentRecord]:
        return self._repo.list_departments(tenant_id=tenant_id)

    def list_roles(self, *, tenant_id: UUID) -> list[RoleRecord]:
        return self._repo.list_roles(tenant_id=tenant_id)

    def get_department(self, *, tenant_id: UUID, department_id: UUID) -> DepartmentRecord | None:
        return self._repo.get_department(tenant_id=tenant_id, department_id=department_id)

    def get_role(self, *, tenant_id: UUID, role_id: UUID) -> RoleRecord | None:
        return self._repo.get_role(tenant_id=tenant_id, role_id=role_id)

    def get_budget_department(
        self, *, tenant_id: UUID, resource_id: UUID
    ) -> BudgetDepartmentLink | None:
        return self._repo.get_budget_link(tenant_id=tenant_id, resource_id=resource_id)

    def resolve_active_approvers(
        self,
        *,
        tenant_id: UUID,
        approval_type: str,
        amount: Decimal | None = None,
        currency: str | None = None,
        department_id: UUID | None = None,
        required_authority: str | None = None,
    ) -> list[ApproverCandidate]:
        """Return eligible active employees. Does not pick a winner."""
        type_needle = approval_type.strip().upper()
        currency_needle = (currency or "").strip().upper() or None
        authority_needle = (required_authority or "").strip().upper() or None
        roles = {role.role_id: role for role in self._repo.list_roles(tenant_id=tenant_id)}
        departments = {
            dept.department_id: dept for dept in self._repo.list_departments(tenant_id=tenant_id)
        }
        employees = {
            emp.employee_id: emp for emp in self._repo.list_employees(tenant_id=tenant_id)
        }
        candidates: list[ApproverCandidate] = []
        seen: set[UUID] = set()
        for authority in self._repo.list_authorities(tenant_id=tenant_id):
            if not authority.is_active:
                continue
            if authority.approval_type.strip().upper() != type_needle:
                continue
            if authority_needle and (authority.authority_code or "").strip().upper() != authority_needle:
                continue
            if currency_needle and authority.currency.strip().upper() != currency_needle:
                continue
            if amount is not None and amount > authority.max_amount:
                continue
            if (
                department_id is not None
                and authority.department_id is not None
                and authority.department_id != department_id
            ):
                continue
            eligible_ids: list[UUID] = []
            if authority.employee_id is not None:
                eligible_ids.append(authority.employee_id)
            if authority.role_id is not None:
                eligible_ids.extend(
                    emp.employee_id
                    for emp in employees.values()
                    if emp.role_id == authority.role_id
                )
            for employee_id in eligible_ids:
                employee = employees.get(employee_id)
                if employee is None or employee.status != "active":
                    continue
                if employee_id in seen:
                    continue
                role = roles.get(employee.role_id)
                if role is None:
                    continue
                seen.add(employee_id)
                dept = departments.get(employee.department_id)
                candidates.append(
                    ApproverCandidate(
                        employee_id=employee.employee_id,
                        employee_number=employee.employee_number,
                        full_name=employee.full_name,
                        email=employee.email,
                        role_name=role.name,
                        role_code=role.code,
                        department_code=None if dept is None else dept.code,
                        authority_code=authority.authority_code,
                        approval_type=authority.approval_type,
                        max_amount=authority.max_amount,
                        currency=authority.currency,
                        resource_id=employee.resource_id,
                    )
                )
        return candidates

    def resolve_approval_authority(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        approval_type: str | None = None,
    ) -> list[ApprovalAuthorityRecord]:
        employee = self._repo.get_employee(tenant_id=tenant_id, employee_id=employee_id)
        if employee is None:
            return []
        type_needle = (approval_type or "").strip().upper()
        matches: list[ApprovalAuthorityRecord] = []
        for authority in self._repo.list_authorities(tenant_id=tenant_id):
            if not authority.is_active:
                continue
            subject = authority.employee_id == employee_id or authority.role_id == employee.role_id
            if not subject:
                continue
            if type_needle and authority.approval_type.strip().upper() != type_needle:
                continue
            matches.append(authority)
        return matches

    def compare_requester_approver(
        self,
        *,
        tenant_id: UUID,
        requester_employee_id: UUID | None,
        approver_employee_id: UUID | None,
    ) -> SodComparison:
        """SoD uses stable employee IDs. Missing approver is not treated as clear."""
        if approver_employee_id is None:
            return SodComparison(
                status="APPROVER_NOT_RESOLVED",
                requester_employee_id=requester_employee_id,
                approver_employee_id=None,
                same_person=False,
            )
        approver = self._repo.get_employee(tenant_id=tenant_id, employee_id=approver_employee_id)
        if approver is None:
            raise ApproverNotResolvedError("APPROVER_NOT_RESOLVED")
        if requester_employee_id is None:
            return SodComparison(
                status="DISTINCT",
                requester_employee_id=None,
                approver_employee_id=approver_employee_id,
                same_person=False,
            )
        requester = self._repo.get_employee(tenant_id=tenant_id, employee_id=requester_employee_id)
        if requester is None:
            return SodComparison(
                status="DISTINCT",
                requester_employee_id=requester_employee_id,
                approver_employee_id=approver_employee_id,
                same_person=False,
            )
        same = requester.employee_id == approver.employee_id
        return SodComparison(
            status="SAME_PERSON" if same else "DISTINCT",
            requester_employee_id=requester.employee_id,
            approver_employee_id=approver.employee_id,
            same_person=same,
        )

    def find_employees_with_skill(
        self,
        *,
        tenant_id: UUID,
        skill_code: str,
        active_only: bool = True,
        available_only: bool = False,
    ) -> list[EmployeeRecord]:
        needle = skill_code.strip().lower()
        results: list[EmployeeRecord] = []
        for employee in self._repo.list_employees(tenant_id=tenant_id):
            if active_only and employee.status != "active":
                continue
            if available_only and not employee.is_available:
                continue
            if needle not in {code.lower() for code in employee.skill_codes}:
                continue
            results.append(employee)
        return results

    def require_tenant_match(self, *, tenant_id: UUID, other_tenant_id: UUID) -> None:
        if tenant_id != other_tenant_id:
            raise CrossTenantDirectoryError("tenant A cannot resolve tenant B directory data")

    def _sync_process_context_identity(self, employee: EmployeeRecord) -> None:
        if employee.user_id is None:
            return
        from app.process_context.identity import IdentityLink, register_identity_link

        register_identity_link(
            IdentityLink(
                tenant_id=employee.tenant_id,
                user_id=employee.user_id,
                employee_id=employee.employee_id,
                employee_resource_id=employee.resource_id,
            )
        )


def _open_runtime_repository() -> CompanyDirectoryRepository:
    from app.core.database import get_sync_session_factory
    from app.core.persistence import PersistenceMode, get_effective_mode
    from app.core.supabase_rest import use_supabase_rest_fallback

    from .db_repository import RestCompanyDirectoryRepository, SqlAlchemyCompanyDirectoryRepository

    mode = get_effective_mode()
    if mode == PersistenceMode.POSTGRES:
        factory = get_sync_session_factory()
        if factory is None:
            raise CompanyDirectoryUnavailableError("Company directory database is unavailable")
        return SqlAlchemyCompanyDirectoryRepository(factory)
    if use_supabase_rest_fallback():
        return RestCompanyDirectoryRepository()
    raise CompanyDirectoryUnavailableError("Company directory database is unavailable")


def get_company_directory() -> CompanyDirectoryService:
    global _DEFAULT_REPO, _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is not None:
        return _DEFAULT_SERVICE
    _DEFAULT_REPO = _open_runtime_repository()
    _DEFAULT_SERVICE = CompanyDirectoryService(_DEFAULT_REPO)
    return _DEFAULT_SERVICE


def reset_company_directory() -> CompanyDirectoryService:
    """Test/dev fixture: isolated in-memory directory. Never a production fallback."""
    global _DEFAULT_REPO, _DEFAULT_SERVICE, _USING_TEST_DIRECTORY
    _USING_TEST_DIRECTORY = True
    _DEFAULT_REPO = InMemoryCompanyDirectoryRepository()
    _DEFAULT_SERVICE = CompanyDirectoryService(_DEFAULT_REPO)
    return _DEFAULT_SERVICE


def configure_company_directory(repository: CompanyDirectoryRepository) -> CompanyDirectoryService:
    global _DEFAULT_REPO, _DEFAULT_SERVICE, _USING_TEST_DIRECTORY
    _USING_TEST_DIRECTORY = False
    _DEFAULT_REPO = repository
    _DEFAULT_SERVICE = CompanyDirectoryService(repository)
    return _DEFAULT_SERVICE
