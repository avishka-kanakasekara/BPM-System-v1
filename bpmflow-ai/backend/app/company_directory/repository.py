"""In-memory company directory store. All operations require tenant_id."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4

from .exceptions import CrossTenantDirectoryError, InvalidManagerError
from .schemas import (
    ApprovalAuthorityRecord,
    BudgetDepartmentLink,
    CreateEmployeeInput,
    DepartmentRecord,
    EmployeeRecord,
    IdentityMapping,
    RoleRecord,
)


class CompanyDirectoryRepository(Protocol):
    def create_department(self, department: DepartmentRecord) -> DepartmentRecord: ...
    def create_role(self, role: RoleRecord) -> RoleRecord: ...
    def create_employee(self, payload: CreateEmployeeInput) -> EmployeeRecord: ...
    def create_authority(self, authority: ApprovalAuthorityRecord) -> ApprovalAuthorityRecord: ...
    def link_identity(self, mapping: IdentityMapping) -> IdentityMapping: ...
    def link_budget_department(self, link: BudgetDepartmentLink) -> BudgetDepartmentLink: ...
    def get_employee(self, *, tenant_id: UUID, employee_id: UUID) -> EmployeeRecord | None: ...
    def get_department(self, *, tenant_id: UUID, department_id: UUID) -> DepartmentRecord | None: ...
    def get_role(self, *, tenant_id: UUID, role_id: UUID) -> RoleRecord | None: ...
    def list_employees(self, *, tenant_id: UUID) -> list[EmployeeRecord]: ...
    def list_departments(self, *, tenant_id: UUID) -> list[DepartmentRecord]: ...
    def list_roles(self, *, tenant_id: UUID) -> list[RoleRecord]: ...
    def list_authorities(self, *, tenant_id: UUID) -> list[ApprovalAuthorityRecord]: ...
    def get_identity_by_user(self, *, tenant_id: UUID, user_id: UUID) -> IdentityMapping | None: ...
    def get_identity_by_employee(self, *, tenant_id: UUID, employee_id: UUID) -> IdentityMapping | None: ...
    def get_budget_link(self, *, tenant_id: UUID, resource_id: UUID) -> BudgetDepartmentLink | None: ...
    def clear(self) -> None: ...


class InMemoryCompanyDirectoryRepository:
    """Tenant-keyed directory used by tests and local development."""

    def __init__(self) -> None:
        self._departments: dict[tuple[UUID, UUID], DepartmentRecord] = {}
        self._roles: dict[tuple[UUID, UUID], RoleRecord] = {}
        self._employees: dict[tuple[UUID, UUID], EmployeeRecord] = {}
        self._authorities: dict[tuple[UUID, UUID], ApprovalAuthorityRecord] = {}
        self._identities: dict[tuple[UUID, UUID], IdentityMapping] = {}
        self._budget_links: dict[tuple[UUID, UUID], BudgetDepartmentLink] = {}

    def clear(self) -> None:
        self._departments.clear()
        self._roles.clear()
        self._employees.clear()
        self._authorities.clear()
        self._identities.clear()
        self._budget_links.clear()

    def create_department(self, department: DepartmentRecord) -> DepartmentRecord:
        self._departments[(department.tenant_id, department.department_id)] = department
        return department

    def create_role(self, role: RoleRecord) -> RoleRecord:
        self._roles[(role.tenant_id, role.role_id)] = role
        return role

    def create_employee(self, payload: CreateEmployeeInput) -> EmployeeRecord:
        tenant_id = payload.tenant_id
        if self.get_department(tenant_id=tenant_id, department_id=payload.department_id) is None:
            raise InvalidManagerError("department not found in tenant", error_code="DEPARTMENT_NOT_FOUND")
        if self.get_role(tenant_id=tenant_id, role_id=payload.role_id) is None:
            raise InvalidManagerError("role not found in tenant", error_code="ROLE_NOT_FOUND")
        employee_id = payload.employee_id or uuid4()
        manager_id = payload.manager_employee_id
        if manager_id is not None:
            if manager_id == employee_id:
                raise InvalidManagerError("employee cannot manage themselves")
            manager = self.get_employee(tenant_id=tenant_id, employee_id=manager_id)
            if manager is None:
                raise InvalidManagerError("manager must belong to the same tenant")
            if self._manager_cycle(tenant_id, employee_id, manager_id):
                raise InvalidManagerError("circular manager relationship is not allowed")
        record = EmployeeRecord(
            employee_id=employee_id,
            tenant_id=tenant_id,
            employee_number=payload.employee_number,
            full_name=payload.full_name,
            email=payload.email,
            phone=payload.phone,
            department_id=payload.department_id,
            role_id=payload.role_id,
            manager_employee_id=manager_id,
            status=payload.status,
            resource_id=payload.resource_id,
            user_id=payload.user_id,
            skill_codes=list(payload.skill_codes),
            is_available=payload.is_available,
            current_workload_pct=payload.current_workload_pct,
            max_workload_pct=payload.max_workload_pct,
        )
        self._employees[(tenant_id, employee_id)] = record
        if payload.user_id is not None:
            self.link_identity(
                IdentityMapping(
                    tenant_id=tenant_id,
                    auth_user_id=payload.user_id,
                    employee_id=employee_id,
                    resource_id=payload.resource_id,
                )
            )
        return record

    def create_authority(self, authority: ApprovalAuthorityRecord) -> ApprovalAuthorityRecord:
        self._authorities[(authority.tenant_id, authority.authority_id)] = authority
        return authority

    def link_identity(self, mapping: IdentityMapping) -> IdentityMapping:
        self._identities[(mapping.tenant_id, mapping.auth_user_id)] = mapping
        if mapping.employee_id is not None:
            employee = self.get_employee(tenant_id=mapping.tenant_id, employee_id=mapping.employee_id)
            if employee is not None:
                self._employees[(mapping.tenant_id, mapping.employee_id)] = employee.model_copy(
                    update={
                        "user_id": mapping.auth_user_id,
                        "resource_id": mapping.resource_id or employee.resource_id,
                    }
                )
        return mapping

    def link_budget_department(self, link: BudgetDepartmentLink) -> BudgetDepartmentLink:
        if self.get_department(tenant_id=link.tenant_id, department_id=link.department_id) is None:
            raise InvalidManagerError("department not found in tenant", error_code="DEPARTMENT_NOT_FOUND")
        self._budget_links[(link.tenant_id, link.resource_id)] = link
        return link

    def get_employee(self, *, tenant_id: UUID, employee_id: UUID) -> EmployeeRecord | None:
        return self._employees.get((tenant_id, employee_id))

    def get_department(self, *, tenant_id: UUID, department_id: UUID) -> DepartmentRecord | None:
        return self._departments.get((tenant_id, department_id))

    def get_role(self, *, tenant_id: UUID, role_id: UUID) -> RoleRecord | None:
        return self._roles.get((tenant_id, role_id))

    def list_employees(self, *, tenant_id: UUID) -> list[EmployeeRecord]:
        return [row for key, row in self._employees.items() if key[0] == tenant_id]

    def list_departments(self, *, tenant_id: UUID) -> list[DepartmentRecord]:
        return [row for key, row in self._departments.items() if key[0] == tenant_id]

    def list_roles(self, *, tenant_id: UUID) -> list[RoleRecord]:
        return [row for key, row in self._roles.items() if key[0] == tenant_id]

    def list_authorities(self, *, tenant_id: UUID) -> list[ApprovalAuthorityRecord]:
        return [row for key, row in self._authorities.items() if key[0] == tenant_id]

    def get_identity_by_user(self, *, tenant_id: UUID, user_id: UUID) -> IdentityMapping | None:
        return self._identities.get((tenant_id, user_id))

    def get_identity_by_employee(self, *, tenant_id: UUID, employee_id: UUID) -> IdentityMapping | None:
        for mapping in self._identities.values():
            if mapping.tenant_id == tenant_id and mapping.employee_id == employee_id:
                return mapping
        return None

    def get_budget_link(self, *, tenant_id: UUID, resource_id: UUID) -> BudgetDepartmentLink | None:
        return self._budget_links.get((tenant_id, resource_id))

    def _manager_cycle(self, tenant_id: UUID, employee_id: UUID, manager_id: UUID) -> bool:
        seen: set[UUID] = set()
        current: UUID | None = manager_id
        while current is not None:
            if current == employee_id:
                return True
            if current in seen:
                return True
            seen.add(current)
            row = self.get_employee(tenant_id=tenant_id, employee_id=current)
            current = None if row is None else row.manager_employee_id
        return False


def assert_same_tenant(tenant_id: UUID, record_tenant: UUID) -> None:
    if tenant_id != record_tenant:
        raise CrossTenantDirectoryError("tenant A cannot resolve tenant B directory data")
