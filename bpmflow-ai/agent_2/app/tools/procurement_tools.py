"""
Agent 2 — Procurement tools backed by Agent 2 process metadata.

# MOCK: There is no live external ERP yet. These tools persist PO drafts,
quotations, and procurement record updates into process_instances.metadata_json
and workflow_events so Agent 2 has a real, queryable execution trail in Supabase.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.persistence import merge_process_metadata, record_workflow_event
from app.tools.schemas import (
    CreatePODraftInput,
    CreatePODraftOutput,
    RequestQuotationInput,
    RequestQuotationOutput,
    UpdateProcurementRecordInput,
    UpdateProcurementRecordOutput,
)


async def create_po_draft(
    session: Optional[AsyncSession], input_data: CreatePODraftInput
) -> CreatePODraftOutput:
    """Create a purchase-order draft and persist it on the process record."""
    now = datetime.now(timezone.utc)
    po_num = f"PO-2026-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "po_number": po_num,
        "vendor_id": input_data.vendor_id,
        "amount": input_data.amount,
        "items_summary": input_data.items_summary,
        "status": "DRAFT",
        "created_at": now.isoformat(),
    }
    await merge_process_metadata(session, input_data.process_id, {"po_drafts": [record]})
    await record_workflow_event(
        session,
        input_data.process_id,
        "PO_DRAFT_CREATED",
        metadata=record,
        new_state="DRAFT",
    )
    return CreatePODraftOutput(
        po_number=po_num,
        status="DRAFT",
        amount=input_data.amount,
        created_at=now.isoformat(),
    )


async def request_quotation(
    session: Optional[AsyncSession], input_data: RequestQuotationInput
) -> RequestQuotationOutput:
    """Request a vendor quotation and persist the RFQ trail."""
    now = datetime.now(timezone.utc)
    quote_id = f"RFQ-2026-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "quotation_id": quote_id,
        "vendor_email": input_data.vendor_email,
        "items": input_data.items,
        "required_by": input_data.required_by,
        "status": "REQUESTED",
        "requested_at": now.isoformat(),
    }
    process_id = getattr(input_data, "process_id", "") or ""
    if process_id:
        await merge_process_metadata(session, process_id, {"quotations": [record]})
        await record_workflow_event(
            session,
            process_id,
            "QUOTATION_REQUESTED",
            metadata=record,
            new_state="REQUESTED",
        )
    return RequestQuotationOutput(
        quotation_id=quote_id,
        status="REQUESTED",
        requested_at=now.isoformat(),
    )


async def update_procurement_record(
    session: Optional[AsyncSession], input_data: UpdateProcurementRecordInput
) -> UpdateProcurementRecordOutput:
    """Update a procurement ERP record stored on the process metadata trail."""
    now = datetime.now(timezone.utc)
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
