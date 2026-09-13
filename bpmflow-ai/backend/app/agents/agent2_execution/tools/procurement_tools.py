"""
Agent 2 — Procurement tools backed by Agent 2 process metadata.

PO drafts and quotations persist on processes.metadata_json with server-side
amount validation. When a real ERP is added, these tools are the seam to replace.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.communication.schemas import EmailRequest
from app.agents.agent2_execution.database.persistence import (
    merge_process_metadata,
    record_workflow_event,
)
from app.agents.agent2_execution.tools.email_service import EmailService
from app.agents.agent2_execution.tools.schemas import (
    CreatePODraftInput,
    CreatePODraftOutput,
    RequestQuotationInput,
    RequestQuotationOutput,
    UpdateProcurementRecordInput,
    UpdateProcurementRecordOutput,
)


def _compute_po_totals(input_data: CreatePODraftInput) -> tuple[float, float, float]:
    """Server-side totals — never trust client-supplied amount."""
    if input_data.items:
        subtotal = round(
            sum(item.quantity * item.unit_price for item in input_data.items), 2
        )
    elif input_data.amount > 0:
        subtotal = round(float(input_data.amount), 2)
    else:
        raise ValueError("PO draft requires line items or a positive amount")
    if subtotal <= 0:
        raise ValueError("PO subtotal must be greater than zero")
    tax = round(subtotal * float(input_data.tax_rate), 2)
    total = round(subtotal + tax, 2)
    return subtotal, tax, total


async def create_po_draft(
    session: AsyncSession | None, input_data: CreatePODraftInput
) -> CreatePODraftOutput:
    """Create a purchase-order draft and persist it on the process record."""
    subtotal, tax, total = _compute_po_totals(input_data)
    now = datetime.now(UTC)
    po_num = f"PO-2026-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "po_number": po_num,
        "po_reference": po_num,
        "vendor_id": input_data.vendor_id,
        "vendor": input_data.vendor_id,
        "amount": total,
        "subtotal": subtotal,
        "tax": tax,
        "tax_rate": input_data.tax_rate,
        "currency": input_data.currency.upper(),
        "items": [i.model_dump() for i in input_data.items] if input_data.items else [],
        "items_summary": input_data.items_summary or (
            ", ".join(i.description for i in input_data.items) if input_data.items else ""
        ),
        "notes": input_data.notes,
        "task_id": input_data.task_id,
        "status": "DRAFT",
        "created_at": now.isoformat(),
    }
    await merge_process_metadata(
        session,
        input_data.process_id,
        {
            "po_drafts": [record],
            "purchase_order": record,
            "last_execution": {
                "tool_name": "create_po_draft",
                "po_number": po_num,
                "amount": total,
                "vendor": input_data.vendor_id,
                "currency": input_data.currency.upper(),
                "status": "DRAFT",
            },
        },
    )
    await record_workflow_event(
        session,
        input_data.process_id,
        "PO_DRAFT_CREATED",
        task_id=input_data.task_id or None,
        metadata=record,
        new_state="DRAFT",
    )
    return CreatePODraftOutput(
        po_number=po_num,
        status="DRAFT",
        amount=total,
        subtotal=subtotal,
        tax=tax,
        currency=input_data.currency.upper(),
        created_at=now.isoformat(),
    )


async def request_quotation(
    session: AsyncSession | None, input_data: RequestQuotationInput
) -> RequestQuotationOutput:
    """Request a vendor quotation and persist the RFQ trail."""
    now = datetime.now(UTC)
    quote_id = f"RFQ-2026-{uuid.uuid4().hex[:6].upper()}"
    process_id = getattr(input_data, "process_id", "") or ""
    task_id = getattr(input_data, "task_id", "") or ""
    record = {
        "quotation_id": quote_id,
        "vendor_email": input_data.vendor_email,
        "items": input_data.items,
        "required_by": input_data.required_by,
        "status": "RECORDED",
        "requested_at": now.isoformat(),
        "process_id": process_id,
        "task_id": task_id,
    }
    email_status = "NOT_SENT"
    final_status = "RECORDED"

    if process_id:
        await merge_process_metadata(session, process_id, {"quotations": [record]})
        await record_workflow_event(
            session,
            process_id,
            "QUOTATION_REQUESTED",
            task_id=task_id or None,
            metadata=record,
            new_state="RECORDED",
        )

    if input_data.vendor_email:
        service = EmailService(session=session)
        body = (
            f"Request for quotation (RFQ {quote_id})\n\n"
            f"Items:\n{input_data.items}\n\n"
            f"Required by: {input_data.required_by or 'as soon as possible'}\n"
        )
        email_result = await service.send_email(
            EmailRequest(
                recipient=input_data.vendor_email,
                subject=f"RFQ {quote_id} — quotation request",
                body=body,
                process_id=process_id or quote_id,
                task_id=task_id or quote_id,
                recipient_role="vendor",
                template_name="task_assignment.html",
            )
        )
        email_status = email_result.status
        record["email_status"] = email_status
        record["email_message_id"] = email_result.message_id
        if email_result.status in {"ACCEPTED_BY_PROVIDER", "DRY_RUN", "SENT"}:
            final_status = "COMMUNICATION_SENT"
        elif email_result.status == "FAILED":
            final_status = "COMMUNICATION_FAILED"
        else:
            final_status = "COMMUNICATION_PENDING"
        record["status"] = final_status
        if process_id:
            await merge_process_metadata(session, process_id, {"quotations": [record]})

    return RequestQuotationOutput(
        quotation_id=quote_id,
        status=final_status,
        email_status=email_status,
        requested_at=now.isoformat(),
    )


async def update_procurement_record(
    session: AsyncSession | None, input_data: UpdateProcurementRecordInput
) -> UpdateProcurementRecordOutput:
    """Update a procurement ERP record stored on the process metadata trail."""
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
