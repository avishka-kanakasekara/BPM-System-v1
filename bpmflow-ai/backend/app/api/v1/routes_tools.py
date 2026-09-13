"""Authenticated tenant-scoped Tool Registry APIs. Resolution is not execution."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.deps import get_tool_registry_service
from app.core.security import get_current_user, require_roles
from app.schemas.auth import CurrentUser
from app.tool_registry.exceptions import (
    ToolAmbiguousError,
    ToolCategoryMismatchError,
    ToolDisabledError,
    ToolNotFoundError,
    ToolNotRegisteredError,
    ToolRegistryError,
    ToolStepTypeNotAllowedError,
)
from app.tool_registry.schemas import RegisterToolInput, ResolveToolInput, ToolRegistryRecord
from app.tool_registry.service import ToolRegistryService

router = APIRouter(prefix="/tools", tags=["tools"])


def _require_tenant(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context is required for tool registry operations",
        )
    return user.tenant_id


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ToolNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    if isinstance(
        exc,
        (
            ToolNotRegisteredError,
            ToolDisabledError,
            ToolAmbiguousError,
            ToolCategoryMismatchError,
            ToolStepTypeNotAllowedError,
            ToolRegistryError,
        ),
    ):
        status_code = (
            status.HTTP_404_NOT_FOUND
            if isinstance(exc, ToolNotRegisteredError)
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        return HTTPException(status_code=status_code, detail=exc.as_dict())
    raise exc


@router.get("", response_model=list[ToolRegistryRecord])
async def list_tools(
    current_user: CurrentUser = Depends(get_current_user),
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> list[ToolRegistryRecord]:
    tenant_id = _require_tenant(current_user)
    return await service.list_tools(tenant_id=tenant_id)


@router.post("/resolve", response_model=ToolRegistryRecord)
async def resolve_tool(
    payload: ResolveToolInput,
    current_user: CurrentUser = Depends(get_current_user),
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolRegistryRecord:
    tenant_id = _require_tenant(current_user)
    try:
        return await service.resolve_action(
            tenant_id=tenant_id,
            action_code=payload.action_code,
            tool_category=payload.tool_category,
            step_type=payload.step_type,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{tool_id}", response_model=ToolRegistryRecord)
async def get_tool(
    tool_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolRegistryRecord:
    tenant_id = _require_tenant(current_user)
    try:
        return await service.get_tool(tool_id, tenant_id=tenant_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("", response_model=ToolRegistryRecord, status_code=status.HTTP_201_CREATED)
async def register_tool(
    payload: RegisterToolInput,
    current_user: CurrentUser = Depends(require_roles("admin")),
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolRegistryRecord:
    tenant_id = _require_tenant(current_user)
    try:
        return await service.register_tool(payload, tenant_id=tenant_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{tool_id}/enable", response_model=ToolRegistryRecord)
async def enable_tool(
    tool_id: UUID,
    current_user: CurrentUser = Depends(require_roles("admin")),
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolRegistryRecord:
    tenant_id = _require_tenant(current_user)
    try:
        return await service.enable_tool(tool_id, tenant_id=tenant_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{tool_id}/disable", response_model=ToolRegistryRecord)
async def disable_tool(
    tool_id: UUID,
    current_user: CurrentUser = Depends(require_roles("admin")),
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolRegistryRecord:
    tenant_id = _require_tenant(current_user)
    try:
        return await service.disable_tool(tool_id, tenant_id=tenant_id)
    except Exception as exc:
        raise _map_error(exc) from exc
