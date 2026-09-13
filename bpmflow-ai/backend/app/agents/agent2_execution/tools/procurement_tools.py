"""Agent 2 procurement tools backed by tenant-scoped procurement tables.

process.metadata_json may store a purchase_order_ref cache only. The
purchase_orders / quotations / vendors tables are the source of truth.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.database.persistence import (
    merge_process_metadata,
    record_workflow_event,
)
from app.agents.agent2_execution.tools.schemas import (
    CreatePODraftInput,
    CreatePODraftOutput,
    RequestQuotationInput,
    RequestQuotationOutput,
    UpdateProcurementRecordInput,
    UpdateProcurementRecordOutput,
)
from app.procurement.exceptions import (
    ProcurementError,
    VendorCommunicationUnavailableError,
)
from app.procurement.schemas import CreatePurchaseOrderInput, CreateQuotationInput, LineItemInput
from app.procurement.service import get_procurement


def _compute_po_totals(input_data: CreatePODraftInput) -> tuple[float, float, float]:
    """Server-side totals — never trust client-supplied amount as line math."""
    if input_data.items:
        subtotal = round(sum(item.quantity * item.unit_price for item in input_data.items), 2)
    elif input_data.amount > 0:
        subtotal = round(float(input_data.amount), 2)
    else:
        raise ValueError("PO draft requires line items or a positive amount")
    if subtotal <= 0:
        raise ValueError("PO subtotal must be greater than zero")
    tax = round(subtotal * float(input_data.tax_rate), 2)
    total = round(subtotal + tax, 2)
    return subtotal, tax, total


def _as_uuid(value: str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _tenant_id(input_data: CreatePODraftInput) -> UUID:
    text = (getattr(input_data, "tenant_id", "") or "").strip()
    if not text:
        raise ProcurementError(
            "tenant_id is required to create a purchase order",
            error_code="MISSING_REQUIRED_EXECUTION_CONTEXT",
        )
    try:
        return UUID(text)
    except ValueError as exc:
        raise ProcurementError(
            "tenant_id is invalid",
            error_code="MISSING_REQUIRED_EXECUTION_CONTEXT",
        ) from exc


async def create_po_draft(
    session: AsyncSession | None, input_data: CreatePODraftInput
) -> CreatePODraftOutput:
    """Create a real PurchaseOrder row. Does not invent vendor or PO numbers."""
    currency = (input_data.currency or "").strip().upper()
    if len(currency) < 3:
        raise ProcurementError(
            "Purchase currency is required",
            error_code="MISSING_REQUIRED_EXECUTION_CONTEXT",
        )
    tenant_id = _tenant_id(input_data)
    process_id = _as_uuid(input_data.process_id)
    subtotal, tax, total = _compute_po_totals(input_data)
    items = [
        LineItemInput(
            description=item.description,
            quantity=Decimal(str(item.quantity)),
            unit_price=Decimal(str(item.unit_price)),
        )
        for item in (input_data.items or [])
    ]
    step_id = getattr(input_data, "workflow_step_id", "") or ""
    plan_id = getattr(input_data, "workflow_plan_id", "") or ""
    budget = getattr(input_data, "budget_available", None)
    procurement = get_procurement()
    record = procurement.create_purchase_order(
        CreatePurchaseOrderInput(
            tenant_id=tenant_id,
            process_id=process_id,
            vendor_ref=input_data.vendor_id,
            currency=currency,
            amount=Decimal(str(total)),
            tax=Decimal(str(tax)),
            workflow_plan_id=None if not plan_id else UUID(str(plan_id)),
            workflow_step_id=None if not step_id else UUID(str(step_id)),
            budget_available=None if budget in (None, "") else Decimal(str(budget)),
            min_quotations=int(getattr(input_data, "min_quotations", 0) or 0),
            notes=input_data.notes,
            created_by=input_data.task_id or None,
            items=items,
            quotation_facts=list(getattr(input_data, "quotation_facts", None) or []),
        )
    )
    now = datetime.now(UTC)
    reference = {
        "id": str(record.purchase_order_id),
        "po_number": record.po_number,
        "vendor_id": input_data.vendor_id,
        "vendor_record_id": str(record.vendor_id),
        "currency": record.currency,
        "total": float(record.total),
        "status": record.status,
        "authoritative": "purchase_orders",
    }
    await merge_process_metadata(
        session,
        input_data.process_id,
        {
            "purchase_order_ref": reference,
            "purchase_order": reference,
            "last_execution": {
                "tool_name": "create_po_draft",
                "po_number": record.po_number,
                "purchase_order_id": str(record.purchase_order_id),
                "status": record.status,
            },
        },
    )
    await record_workflow_event(
        session,
        input_data.process_id,
        "PO_DRAFT_CREATED",
        task_id=input_data.task_id or None,
        metadata=reference,
        new_state="DRAFT",
    )
    return CreatePODraftOutput(
        po_number=record.po_number,
        status=record.status,
        amount=float(record.total),
        subtotal=float(record.subtotal),
        tax=float(record.tax),
        currency=record.currency,
        created_at=(record.created_at or now).isoformat(),
        purchase_order_id=str(record.purchase_order_id),
    )


async def request_quotation(
    session: AsyncSession | None, input_data: RequestQuotationInput
) -> RequestQuotationOutput:
    """Record a quotation requirement. Does not invent vendor email or send unless verified."""
    now = datetime.now(UTC)
    process_id = getattr(input_data, "process_id", "") or ""
    task_id = getattr(input_data, "task_id", "") or ""
    tenant_text = (getattr(input_data, "tenant_id", "") or "").strip()
    vendor_ref = (getattr(input_data, "vendor_id", "") or "").strip()
    currency = (getattr(input_data, "currency", "") or "").strip().upper()
    email_status = "NOT_SENT"
    final_status = "RECORDED"
    quote_id = f"RFQ-{uuid4().hex[:8].upper()}"
    persisted_id = quote_id

    if tenant_text and process_id and vendor_ref and currency:
        procurement = get_procurement()
        tenant_id = UUID(tenant_text)
        vendor = procurement.resolve_vendor(tenant_id=tenant_id, vendor_ref=vendor_ref)
        contacts = procurement.list_vendor_contacts(tenant_id=tenant_id, vendor_id=vendor.vendor_id)
        verified_emails = {
            (contact.email or "").strip().lower()
            for contact in contacts
            if contact.is_active and contact.email
        }
        caller_email = (input_data.vendor_email or "").strip().lower()
        record = procurement.create_quotation(
            CreateQuotationInput(
                tenant_id=tenant_id,
                vendor_id=vendor.vendor_id,
                process_id=UUID(process_id),
                currency=currency,
                quotation_number=quote_id,
                status="REQUESTED",
                items=[],
            )
        )
        persisted_id = str(record.quotation_id)
        if caller_email and caller_email not in verified_emails:
            final_status = VendorCommunicationUnavailableError.error_code
        elif not verified_emails:
            final_status = VendorCommunicationUnavailableError.error_code
        else:
            final_status = "RECORDED"
            email_status = "NOT_SENT"
        await merge_process_metadata(
            session,
            process_id,
            {
                "quotation_refs": [
                    {
                        "id": persisted_id,
                        "quotation_number": record.quotation_number,
                        "status": record.status,
                    }
                ]
            },
        )
        await record_workflow_event(
            session,
            process_id,
            "QUOTATION_REQUESTED",
            task_id=task_id or None,
            metadata={"quotation_id": persisted_id, "status": final_status},
            new_state=final_status,
        )
        return RequestQuotationOutput(
            quotation_id=persisted_id,
            status=final_status,
            email_status=email_status,
            requested_at=now.isoformat(),
        )

    if process_id:
        await merge_process_metadata(
            session,
            process_id,
            {
                "quotation_refs": [
                    {
                        "status": VendorCommunicationUnavailableError.error_code,
                        "reason": "tenant, vendor, currency, and process are required to persist a quotation",
                    }
                ]
            },
        )
    return RequestQuotationOutput(
        quotation_id=quote_id,
        status=VendorCommunicationUnavailableError.error_code,
        email_status=email_status,
        requested_at=now.isoformat(),
    )


async def update_procurement_record(
    session: AsyncSession | None, input_data: UpdateProcurementRecordInput
) -> UpdateProcurementRecordOutput:
    """Legacy ERP-status trail on process metadata. Not a purchase-order source of truth."""
    now = datetime.now(UTC)
    record = {
        "record_id": input_data.record_id,
        "status": input_data.status,
        "notes": input_data.notes,
        "updated_at": now.isoformat(),
    }
    process_id = getattr(input_data, "process_id", "") or input_data.record_id
    await merge_process_metadata(
        session,
        process_id,
        {"erp_records": {input_data.record_id: record}},
    )
    await record_workflow_event(
        session,
        process_id,
        "PROCUREMENT_RECORD_UPDATED",
        metadata=record,
        new_state=input_data.status,
    )
    return UpdateProcurementRecordOutput(
        record_id=input_data.record_id,
        status=input_data.status,
        updated_at=now.isoformat(),
    )
