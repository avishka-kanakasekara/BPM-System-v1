"""Agent 2 MATCH_INVOICE tool. Runs InvoiceMatchingService only."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.database.persistence import merge_process_metadata
from app.agents.agent2_execution.tools.schemas import MatchInvoiceInput, MatchInvoiceOutput
from app.procurement.exceptions import InvoiceNotFoundError, ProcurementError, PurchaseOrderNotFoundError
from app.procurement.service import get_procurement


async def match_invoice(
    session: AsyncSession | None, input_data: MatchInvoiceInput
) -> MatchInvoiceOutput:
    """Deterministic PO ↔ Invoice match. Does not invent invoices or change ProcessContext."""
    tenant_text = (input_data.tenant_id or "").strip()
    if not tenant_text:
        raise ProcurementError(
            "tenant_id is required to match an invoice",
            error_code="MISSING_REQUIRED_EXECUTION_CONTEXT",
        )
    tenant_id = UUID(tenant_text)
    process_id = UUID(str(input_data.process_id))
    procurement = get_procurement()
    invoice_id_text = (input_data.invoice_id or "").strip()
    if invoice_id_text:
        invoice = procurement.get_invoice(tenant_id=tenant_id, invoice_id=UUID(invoice_id_text))
    else:
        invoices = procurement.list_invoices(tenant_id=tenant_id, process_id=process_id)
        invoice = invoices[0] if invoices else None
    if invoice is None:
        raise InvoiceNotFoundError("No invoice exists for this process")
    po = procurement.get_purchase_order_for_process(tenant_id=tenant_id, process_id=process_id)
    if po is None:
        raise PurchaseOrderNotFoundError("No purchase order exists for this process")
    result = procurement.match_invoice(
        tenant_id=tenant_id,
        invoice_id=invoice.invoice_id,
        trace_id=input_data.trace_id or None,
    )
    await merge_process_metadata(
        session,
        str(process_id),
        {
            "invoice_match_ref": {
                "invoice_id": str(result.invoice_id),
                "purchase_order_id": str(result.purchase_order_id),
                "status": result.status,
                "authoritative": "invoices",
            }
        },
    )
    from app.agents.agent2_execution.security.audit import log_audit_event

    await log_audit_event(
        session,
        actor="agent_2",
        action="match_invoice",
        allowed=True,
        reason=f"PO ↔ Invoice match status={result.status}",
        payload={
            "tenant_id": str(tenant_id),
            "process_id": str(process_id),
            "invoice_id": str(result.invoice_id),
            "purchase_order_id": str(result.purchase_order_id),
            "status": result.status,
            "discrepancy_codes": list(result.discrepancy_codes),
            "trace_id": result.trace_id,
        },
    )
    return MatchInvoiceOutput(
        invoice_id=str(result.invoice_id),
        purchase_order_id=str(result.purchase_order_id),
        status=result.status,
        matched=result.matched,
        discrepancy_codes=list(result.discrepancy_codes),
        discrepancy_details=list(result.discrepancy_details),
        invoice_amount=None if result.invoice_amount is None else float(result.invoice_amount),
        po_amount=None if result.po_amount is None else float(result.po_amount),
        currency=result.currency,
        trace_id=result.trace_id,
    )
