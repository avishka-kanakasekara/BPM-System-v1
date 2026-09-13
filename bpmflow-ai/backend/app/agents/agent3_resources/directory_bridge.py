"""Map CompanyDirectory employees onto Agent 3 HUMAN evidence.

When a tenant has company employees, those records are the identity source.
Repository resources only enrich linked employees; unlinked synthetic humans
are not mixed into a company-directory tenant.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.company_directory.schemas import EmployeeRecord
from app.company_directory.service import CompanyDirectoryService

from .constants import ResourceType
from .schemas import HumanResourceEvidence, HumanResourceRequirement


def _norm(value: str | None) -> str:
    return (value or "").strip().lower().replace("_", " ")


def role_tokens(values: list[str] | None) -> set[str]:
    return {_norm(item) for item in (values or []) if item and item.strip()}


def human_requirement_is_incomplete(requirement: HumanResourceRequirement) -> bool:
    if requirement.assignment_kind == "approver" and requirement.required_approval_type:
        return False
    has_role = bool(requirement.required_roles)
    has_dept = bool(requirement.required_department_code or requirement.required_department_id)
    has_skill = bool(requirement.mandatory_skills)
    has_authority = bool(
        requirement.required_authority
        or requirement.required_authority_code
        or requirement.minimum_authority_amount is not None
    )
    return not (has_role or has_dept or has_skill or has_authority)


def evidence_from_employee(
    employee: EmployeeRecord,
    directory: CompanyDirectoryService,
    *,
    evaluation_timestamp: datetime,
    linked_resource: HumanResourceEvidence | None = None,
) -> HumanResourceEvidence:
    """Build HUMAN evidence from verified company data. Never invents email."""
    role = directory.get_role(tenant_id=employee.tenant_id, role_id=employee.role_id)
    department = directory.get_department(
        tenant_id=employee.tenant_id, department_id=employee.department_id
    )
    role_names = []
    if role is not None:
        role_names.extend([role.name, role.code])
    authorities = directory.resolve_approval_authority(
        tenant_id=employee.tenant_id, employee_id=employee.employee_id
    )
    employee_scoped = [item for item in authorities if item.employee_id == employee.employee_id]
    if employee_scoped:
        authorities = employee_scoped
    max_amount = None
    currency = None
    authority_code = None
    if authorities:
        best = max(authorities, key=lambda item: item.max_amount)
        max_amount = best.max_amount
        currency = best.currency
        authority_code = best.authority_code or best.approval_type
    if linked_resource is not None:
        authority_code = authority_code or linked_resource.authority
        skills = list(dict.fromkeys([*employee.skill_codes, *linked_resource.mandatory_skills]))
        preferred = list(linked_resource.preferred_skills)
        roles = list(dict.fromkeys([*role_names, *linked_resource.roles]))
        resource_id = linked_resource.resource_id
        available_from = linked_resource.available_from
        available_until = linked_resource.available_until
        current = linked_resource.current_workload_percentage
        max_wl = linked_resource.max_workload_percentage
        evidence_checked = linked_resource.evidence_checked_at
        evidence_valid = linked_resource.evidence_valid_until
        refs = dict(linked_resource.evidence_references)
        is_active = employee.status == "active" and linked_resource.is_active
    else:
        skills = list(employee.skill_codes)
        preferred = []
        roles = role_names
        resource_id = employee.resource_id or employee.employee_id
        if employee.is_available:
            available_from = evaluation_timestamp - timedelta(hours=1)
            available_until = evaluation_timestamp + timedelta(days=365)
        else:
            available_from = evaluation_timestamp + timedelta(days=365)
            available_until = None
        current = employee.current_workload_pct if employee.current_workload_pct is not None else Decimal("0")
        max_wl = employee.max_workload_pct if employee.max_workload_pct is not None else Decimal("100")
        evidence_checked = evaluation_timestamp - timedelta(days=1)
        evidence_valid = evaluation_timestamp + timedelta(days=90)
        refs = {
            "source": "company_directory",
            "availability": {"verified_at": evaluation_timestamp.isoformat()},
            "workload": {"verified_at": evaluation_timestamp.isoformat()},
        }
        is_active = employee.status == "active"
    refs["company_directory"] = {
        "employee_id": str(employee.employee_id),
        "employee_number": employee.employee_number,
    }
    return HumanResourceEvidence(
        resource_id=resource_id,
        tenant_id=employee.tenant_id,
        resource_type=ResourceType.HUMAN,
        name=employee.full_name,
        is_active=is_active,
        roles=roles,
        mandatory_skills=skills,
        preferred_skills=preferred,
        authority=authority_code,
        available_from=available_from,
        available_until=available_until,
        current_workload_percentage=current,
        max_workload_percentage=max_wl,
        projected_workload_percentage=current,
        evidence_checked_at=evidence_checked,
        evidence_valid_until=evidence_valid,
        evidence_references=refs,
        employee_id=employee.employee_id,
        employee_number=employee.employee_number,
        employee_email=employee.email,
        department_code=None if department is None else department.code,
        department_id=employee.department_id,
        authority_max_amount=max_amount,
        authority_currency=currency,
    )


def load_directory_candidates(
    directory: CompanyDirectoryService,
    *,
    tenant_id: UUID,
    evaluation_timestamp: datetime,
    repository_resources: list[HumanResourceEvidence],
) -> list[HumanResourceEvidence]:
    employees = directory.list_employees(tenant_id=tenant_id)
    if not employees:
        return [item for item in repository_resources if item.tenant_id == tenant_id]
    by_resource = {item.resource_id: item for item in repository_resources if item.tenant_id == tenant_id}
    candidates: list[HumanResourceEvidence] = []
    for employee in employees:
        if employee.tenant_id != tenant_id:
            continue
        linked = None
        if employee.resource_id is not None:
            linked = by_resource.get(employee.resource_id)
        candidates.append(
            evidence_from_employee(
                employee,
                directory,
                evaluation_timestamp=evaluation_timestamp,
                linked_resource=linked,
            )
        )
    return candidates
