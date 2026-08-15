"""
Agent 2 — Mock ERP & Procurement Tools

# MOCK: stands in for real ERP integration; swap the body for a real call when real ERP exists —
the signature and the guard/registry contract shouldn't need to change.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

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
    """
    # MOCK: Generate purchase order draft in mock ERP.
    """
    now = datetime.now(timezone.utc)
    po_num = f"PO-2026-{uuid.uuid4().hex[:6].upper()}"

    return CreatePODraftOutput(
        po_number=po_num,
        status="DRAFT",
        amount=input_data.amount,
        created_at=now.isoformat(),
    )


async def request_quotation(
    session: Optional[AsyncSession], input_data: RequestQuotationInput
) -> RequestQuotationOutput:
    """
    # MOCK: Request vendor quotation.
    """
    now = datetime.now(timezone.utc)
    quote_id = f"RFQ-2026-{uuid.uuid4().hex[:6].upper()}"

    return RequestQuotationOutput(
        quotation_id=quote_id,
        status="REQUESTED",
        requested_at=now.isoformat(),
    )


async def update_procurement_record(
    session: Optional[AsyncSession], input_data: UpdateProcurementRecordInput
) -> UpdateProcurementRecordOutput:
    """
    # MOCK: Update procurement ERP record metadata.
    """
    now = datetime.now(timezone.utc)

    return UpdateProcurementRecordOutput(
        record_id=input_data.record_id,
        status=input_data.status,
        updated_at=now.isoformat(),
    )
