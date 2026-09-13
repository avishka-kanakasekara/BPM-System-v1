"""Authenticated vendor APIs. PO creation is not exposed here."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.security import get_current_user, require_roles
from app.procurement.exceptions import ProcurementError
from app.procurement.schemas import CreateInvoiceInput, CreateVendorInput, VendorRecord
from app.procurement.seed import seed_bpmflow_demo_procurement
from app.procurement.service import ProcurementService, get_procurement
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/vendors", tags=["procurement"])


def _require_tenant(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context is required for procurement operations",
        )
    return user.tenant_id


def get_procurement_service() -> ProcurementService:
    return get_procurement()


@router.get("")
def list_vendors(
    current_user: CurrentUser = Depends(get_current_user),
    procurement: ProcurementService = Depends(get_procurement_service),
) -> list[VendorRecord]:
    return procurement.list_vendors(tenant_id=_require_tenant(current_user))


@router.get("/{vendor_id}")
def get_vendor(
    vendor_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    procurement: ProcurementService = Depends(get_procurement_service),
) -> VendorRecord:
    tenant_id = _require_tenant(current_user)
    vendor = procurement.get_vendor(tenant_id=tenant_id, vendor_id=vendor_id)
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    return vendor


@router.post("", status_code=status.HTTP_201_CREATED)
def create_vendor(
    payload: CreateVendorInput,
    current_user: CurrentUser = Depends(require_roles("admin")),
    procurement: ProcurementService = Depends(get_procurement_service),
) -> VendorRecord:
    tenant_id = _require_tenant(current_user)
    if payload.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create vendors for another tenant",
        )
    try:
        return procurement.create_vendor(payload)
    except ProcurementError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.as_dict()) from exc


@router.post("/seed-demo", status_code=status.HTTP_201_CREATED)
def seed_demo_procurement(
    current_user: CurrentUser = Depends(require_roles("admin")),
    procurement: ProcurementService = Depends(get_procurement_service),
):
    env = (settings.ENV or "").strip().lower()
    if env in {"production", "prod"} and not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo procurement seed is not allowed in production",
        )
    _require_tenant(current_user)
    tenant_id = seed_bpmflow_demo_procurement(procurement)
    return {"tenant_id": str(tenant_id), "seeded": True}


invoice_router = APIRouter(prefix="/invoices", tags=["procurement"])


@invoice_router.get("/{invoice_id}")
def get_invoice(
    invoice_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    procurement: ProcurementService = Depends(get_procurement_service),
):
    tenant_id = _require_tenant(current_user)
    invoice = procurement.get_invoice(tenant_id=tenant_id, invoice_id=invoice_id)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


@invoice_router.post("", status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: CreateInvoiceInput,
    current_user: CurrentUser = Depends(require_roles("admin")),
    procurement: ProcurementService = Depends(get_procurement_service),
):
    """Persist an invoice. Does not mark MATCHED."""
    tenant_id = _require_tenant(current_user)
    if payload.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create invoices for another tenant",
        )
    try:
        return procurement.create_invoice(payload)
    except ProcurementError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.as_dict()) from exc
