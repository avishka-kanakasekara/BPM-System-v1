"""Auth user vs company employee/resource mapping (Phase 2 hook).

Phase 1 never invents employee rows. Unmapped users keep employee_resource_id=None.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IdentityLink(BaseModel):
    """Auth user ↔ company employee ↔ Agent 3 resource. IDs stay distinct."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    user_id: UUID
    employee_id: UUID | None = None
    employee_resource_id: UUID | None = None


_IN_MEMORY_LINKS: dict[tuple[UUID, UUID], UUID] = {}
_IN_MEMORY_EMPLOYEE_LINKS: dict[tuple[UUID, UUID], UUID] = {}


def register_identity_link(link: IdentityLink) -> None:
    """Register a verified mapping. Never invents employee or resource IDs."""
    key = (link.tenant_id, link.user_id)
    if link.employee_resource_id is None and link.employee_id is None:
        _IN_MEMORY_LINKS.pop(key, None)
        _IN_MEMORY_EMPLOYEE_LINKS.pop(key, None)
        return
    if link.employee_resource_id is not None:
        _IN_MEMORY_LINKS[key] = link.employee_resource_id
    if link.employee_id is not None:
        _IN_MEMORY_EMPLOYEE_LINKS[key] = link.employee_id


def clear_identity_links() -> None:
    _IN_MEMORY_LINKS.clear()
    _IN_MEMORY_EMPLOYEE_LINKS.clear()


def resolve_employee_id(
    *,
    user_id: UUID | None,
    tenant_id: UUID | None,
) -> UUID | None:
    if user_id is None or tenant_id is None:
        return None
    mapped = _IN_MEMORY_EMPLOYEE_LINKS.get((tenant_id, user_id))
    if mapped is not None:
        return mapped
    try:
        from app.company_directory.service import get_company_directory

        employee = get_company_directory().resolve_employee_by_user_id(
            tenant_id=tenant_id, user_id=user_id
        )
    except Exception:
        return None
    return None if employee is None else employee.employee_id


def resolve_employee_resource_id(
    *,
    user_id: UUID | None,
    tenant_id: UUID | None,
    stored_links: dict[tuple[UUID, UUID], UUID] | None = None,
) -> UUID | None:
    """Return mapped resource id, or None when no verified mapping exists."""
    if user_id is None or tenant_id is None:
        return None
    table = stored_links if stored_links is not None else _IN_MEMORY_LINKS
    mapped = table.get((tenant_id, user_id))
    if mapped is not None:
        return mapped
    if stored_links is not None:
        return None
    try:
        from app.company_directory.service import get_company_directory

        employee = get_company_directory().resolve_employee_by_user_id(
            tenant_id=tenant_id, user_id=user_id
        )
    except Exception:
        return None
    return None if employee is None else employee.resource_id
