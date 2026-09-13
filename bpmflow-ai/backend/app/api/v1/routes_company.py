"""Authenticated company directory APIs. Read-only for tenant users; admin writes."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.company_directory.exceptions import ApproverNotResolvedError, CompanyDirectoryUnavailableError, DirectoryError
from app.company_directory.schemas import CreateEmployeeInput, EmployeeRecord
from app.company_directory.seed import seed_bpmflow_demo_company
from app.company_directory.service import CompanyDirectoryService, get_company_directory
from app.core.config import settings
from app.core.security import get_current_user, require_roles
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/company", tags=["company"])


def _require_tenant(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context is required for company directory operations",
        )
    return user.tenant_id


def get_directory_service() -> CompanyDirectoryService:
    try:
        return get_company_directory()
    except CompanyDirectoryUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.as_dict(),
        ) from exc


@router.get("/employees")
def list_employees(
    current_user: CurrentUser = Depends(get_current_user),
    directory: CompanyDirectoryService = Depends(get_directory_service),
) -> list[EmployeeRecord]:
    tenant_id = _require_tenant(current_user)
    return directory.list_employees(tenant_id=tenant_id)


@router.get("/employees/{employee_id}")
def get_employee(
    employee_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    directory: CompanyDirectoryService = Depends(get_directory_service),
) -> EmployeeRecord:
    tenant_id = _require_tenant(current_user)
    employee = directory.resolve_employee_by_employee_id(
        tenant_id=tenant_id, employee_id=employee_id
    )
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return employee


@router.post("/employees", status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: CreateEmployeeInput,
    current_user: CurrentUser = Depends(require_roles("admin")),
    directory: CompanyDirectoryService = Depends(get_directory_service),
) -> EmployeeRecord:
    tenant_id = _require_tenant(current_user)
    if payload.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create employees for another tenant",
        )
    try:
        return directory.create_employee(payload)
    except DirectoryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.as_dict()) from exc


@router.get("/departments")
def list_departments(
    current_user: CurrentUser = Depends(get_current_user),
    directory: CompanyDirectoryService = Depends(get_directory_service),
):
    tenant_id = _require_tenant(current_user)
    return directory.list_departments(tenant_id=tenant_id)


@router.get("/roles")
def list_roles(
    current_user: CurrentUser = Depends(get_current_user),
    directory: CompanyDirectoryService = Depends(get_directory_service),
):
    tenant_id = _require_tenant(current_user)
    return directory.list_roles(tenant_id=tenant_id)


@router.get("/approvers")
def list_approvers(
    approval_type: str = Query(..., min_length=1),
    amount: Decimal | None = Query(default=None),
    currency: str | None = Query(default=None),
    department_id: UUID | None = Query(default=None),
    required_authority: str | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    directory: CompanyDirectoryService = Depends(get_directory_service),
):
    tenant_id = _require_tenant(current_user)
    return directory.resolve_active_approvers(
        tenant_id=tenant_id,
        approval_type=approval_type,
        amount=amount,
        currency=currency,
        department_id=department_id,
        required_authority=required_authority,
    )


@router.get("/sod")
def compare_sod(
    requester_employee_id: UUID,
    approver_employee_id: UUID | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    directory: CompanyDirectoryService = Depends(get_directory_service),
):
    tenant_id = _require_tenant(current_user)
    try:
        return directory.compare_requester_approver(
            tenant_id=tenant_id,
            requester_employee_id=requester_employee_id,
            approver_employee_id=approver_employee_id,
        )
    except ApproverNotResolvedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.as_dict()) from exc


@router.post("/seed-demo", status_code=status.HTTP_201_CREATED)
def seed_demo_company(
    current_user: CurrentUser = Depends(require_roles("admin")),
    directory: CompanyDirectoryService = Depends(get_directory_service),
):
    """Explicit development/demo seed. Disabled in production."""
    env = (settings.ENV or "").strip().lower()
    if env in {"production", "prod"} and not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo company seed is not allowed in production",
        )
    _require_tenant(current_user)
    tenant_id = seed_bpmflow_demo_company(directory)
    return {"tenant_id": str(tenant_id), "seeded": True}
