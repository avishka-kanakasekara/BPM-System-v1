"""Tenant visibility helpers. JWT tenant is the only authority source."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.core.config import settings
from app.schemas.auth import CurrentUser


def authenticated_tenant_id(user: CurrentUser, *, required: bool = False) -> UUID | None:
    """Return JWT tenant_id. Never reads a request-body tenant."""
    if user.tenant_id is not None:
        return user.tenant_id
    if required or settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context must come from the authenticated session",
        )
    return None


def process_visible_to_user(process, user: CurrentUser) -> bool:
    """True when the process is in the caller's tenant (or unscoped in non-prod tests)."""
    process_tenant = getattr(process, "tenant_id", None)
    if user.tenant_id is None:
        return not settings.is_production
    if process_tenant is None:
        return True
    return process_tenant == user.tenant_id


def deny_foreign_process(process, user: CurrentUser) -> None:
    if not process_visible_to_user(process, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process not found")
