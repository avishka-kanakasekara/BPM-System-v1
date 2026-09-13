"""Deterministic PO ↔ Invoice matching. No LLM. No goods-receipt (none exists).

Amount rule: NUMERIC values quantized to 0.01 (currency minor units). That is exact
cent comparison, not a percentage tolerance. If an active policy rule sets
invoice_amount_tolerance / amount_tolerance, that absolute Decimal is used.
"""

from __future__ import annotations

from contextlib import nullcontext
from decimal import Decimal
from uuid import UUID
from uuid import uuid4

from app.core.logging import get_logger

from .exceptions import (
    CrossTenantProcurementError,
    InvoiceNotFoundError,
    PurchaseOrderNotFoundError,
)
from .repository import ProcurementRepository
from .schemas import InvoiceMatchResultRecord, InvoiceRecord, PurchaseOrderRecord

logger = get_logger(__name__)
EXACT_CENT = Decimal("0.00")


def _money(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _norm_desc(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


class InvoiceMatchingService:
    """Compare persisted invoices to persisted purchase orders."""

    def __init__(self, repository: ProcurementRepository) -> None:
        self._repo = repository

    def match(
        self,
        *,
        tenant_id: UUID,
        invoice_id: UUID,
        amount_tolerance: Decimal | None = None,
        trace_id: str | None = None,
    ) -> InvoiceMatchResultRecord:
        lock = getattr(self._repo, "_lock", None)
        with lock if lock is not None else nullcontext():
            return self._match_locked(
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                amount_tolerance=amount_tolerance,
                trace_id=trace_id,
            )

    def _match_locked(
        self,
        *,
        tenant_id: UUID,
        invoice_id: UUID,
        amount_tolerance: Decimal | None,
        trace_id: str | None,
    ) -> InvoiceMatchResultRecord:
        invoice = self._repo.get_invoice(tenant_id=tenant_id, invoice_id=invoice_id)
        if invoice is None:
            other = self._repo.find_invoice_by_id(invoice_id)
            if other is not None:
                raise CrossTenantProcurementError("Invoice belongs to another tenant")
            raise InvoiceNotFoundError("Invoice not found in tenant")
        if invoice.tenant_id != tenant_id:
            raise CrossTenantProcurementError("Invoice belongs to another tenant")
        po = self._repo.get_purchase_order(
            tenant_id=tenant_id, purchase_order_id=invoice.purchase_order_id
        )
        if po is None:
            result = self._result(
                invoice,
                None,
                status="MISMATCH",
                codes=["MISSING_PO"],
                details=["Purchase order was not found in tenant"],
                tolerance=amount_tolerance,
                trace_id=trace_id,
            )
            self._persist(invoice, result)
            return result
        if po.tenant_id != tenant_id or invoice.process_id != po.process_id:
            raise CrossTenantProcurementError("Invoice and purchase order tenants do not match")
        if invoice.match_result and invoice.status in {"MATCHED", "MISMATCH"}:
            stored = InvoiceMatchResultRecord.model_validate(invoice.match_result)
            if stored.invoice_id == invoice.invoice_id and stored.purchase_order_id == po.purchase_order_id:
                return stored
        result = self._compare(invoice, po, amount_tolerance=amount_tolerance, trace_id=trace_id)
        self._persist(invoice, result)
        return result

    def _compare(
        self,
        invoice: InvoiceRecord,
        po: PurchaseOrderRecord,
        *,
        amount_tolerance: Decimal | None,
        trace_id: str | None,
    ) -> InvoiceMatchResultRecord:
        codes: list[str] = []
        details: list[str] = []
        tolerance = amount_tolerance if amount_tolerance is not None else EXACT_CENT
        vendor_match = invoice.vendor_id == po.vendor_id
        if not vendor_match:
            codes.append("VENDOR_MISMATCH")
            details.append(f"vendor mismatch: po={po.vendor_id} invoice={invoice.vendor_id}")
        po_ccy = (po.currency or "").strip().upper()
        inv_ccy = (invoice.currency or "").strip().upper()
        if po_ccy != inv_ccy:
            codes.append("CURRENCY_MISMATCH")
            details.append(f"currency mismatch: po={po_ccy} invoice={inv_ccy}")
        item_sum = sum((item.line_total for item in invoice.items), Decimal("0"))
        if invoice.items:
            expected_subtotal = _money(item_sum)
            if expected_subtotal != _money(invoice.subtotal):
                codes.append("INVOICE_TOTAL_INVALID")
                details.append(
                    f"sum(invoice_items)={expected_subtotal} subtotal={_money(invoice.subtotal)}"
                )
            if _money(invoice.subtotal + invoice.tax) != _money(invoice.total):
                codes.append("INVOICE_TOTAL_INVALID")
                details.append(
                    f"subtotal+tax={_money(invoice.subtotal + invoice.tax)} total={_money(invoice.total)}"
                )
        po_total = _money(po.total)
        inv_total = _money(invoice.total)
        if abs(po_total - inv_total) > tolerance:
            codes.append("AMOUNT_MISMATCH")
            details.append(f"amount mismatch: po={po_total} invoice={inv_total}")
        line_ok = self._match_lines(invoice, po, codes, details, tolerance)
        unique_codes = list(dict.fromkeys(codes))
        status = "MATCHED" if not unique_codes else "MISMATCH"
        return self._result(
            invoice,
            po,
            status=status,
            codes=unique_codes,
            details=details,
            tolerance=tolerance,
            trace_id=trace_id,
            vendor_match=vendor_match,
            line_match=line_ok and "MISSING_INVOICE_ITEM" not in unique_codes
            and "QUANTITY_MISMATCH" not in unique_codes
            and "UNIT_PRICE_MISMATCH" not in unique_codes
            and "LINE_TOTAL_MISMATCH" not in unique_codes
            and "MISSING_PO_ITEM" not in unique_codes,
        )

    def _match_lines(
        self,
        invoice: InvoiceRecord,
        po: PurchaseOrderRecord,
        codes: list[str],
        details: list[str],
        tolerance: Decimal,
    ) -> bool:
        if not po.items and not invoice.items:
            return True
        if po.items and not invoice.items:
            codes.append("MISSING_INVOICE_ITEM")
            details.append("PO has line items but invoice has none")
            return False
        if invoice.items and not po.items:
            codes.append("MISSING_PO_ITEM")
            details.append("Invoice has line items but PO has none")
            return False
        used_po: set[UUID] = set()
        ok = True
        for inv_item in invoice.items:
            po_item = None
            if inv_item.purchase_order_item_id is not None:
                po_item = next(
                    (row for row in po.items if row.item_id == inv_item.purchase_order_item_id),
                    None,
                )
                if po_item is None:
                    codes.append("MISSING_PO_ITEM")
                    details.append(f"invoice item has unknown PO item {inv_item.purchase_order_item_id}")
                    ok = False
                    continue
            else:
                desc = _norm_desc(inv_item.description)
                po_item = next(
                    (
                        row
                        for row in po.items
                        if row.item_id not in used_po and _norm_desc(row.description) == desc
                    ),
                    None,
                )
                if po_item is None:
                    codes.append("MISSING_PO_ITEM")
                    details.append(f"no PO line for invoice item '{inv_item.description}'")
                    ok = False
                    continue
            used_po.add(po_item.item_id)
            if inv_item.quantity != po_item.quantity:
                codes.append("QUANTITY_MISMATCH")
                details.append(
                    f"quantity mismatch: po={po_item.quantity} invoice={inv_item.quantity}"
                )
                ok = False
            if _money(inv_item.unit_price) != _money(po_item.unit_price):
                codes.append("UNIT_PRICE_MISMATCH")
                details.append(
                    f"unit price mismatch: po={po_item.unit_price} invoice={inv_item.unit_price}"
                )
                ok = False
            if abs(_money(inv_item.line_total) - _money(po_item.line_total)) > tolerance:
                codes.append("LINE_TOTAL_MISMATCH")
                details.append(
                    f"line total mismatch: po={po_item.line_total} invoice={inv_item.line_total}"
                )
                ok = False
        if len(used_po) < len(po.items):
            codes.append("MISSING_INVOICE_ITEM")
            details.append("one or more PO lines are missing from the invoice")
            ok = False
        return ok

    def _result(
        self,
        invoice: InvoiceRecord,
        po: PurchaseOrderRecord | None,
        *,
        status: str,
        codes: list[str],
        details: list[str],
        tolerance: Decimal | None,
        trace_id: str | None,
        vendor_match: bool = False,
        line_match: bool = False,
    ) -> InvoiceMatchResultRecord:
        return InvoiceMatchResultRecord(
            invoice_id=invoice.invoice_id,
            purchase_order_id=invoice.purchase_order_id,
            process_id=invoice.process_id,
            tenant_id=invoice.tenant_id,
            status=status,
            matched=status == "MATCHED",
            discrepancy_codes=codes,
            discrepancy_details=details,
            matched_amount=_money(invoice.total) if status == "MATCHED" else None,
            invoice_amount=_money(invoice.total),
            po_amount=None if po is None else _money(po.total),
            currency=invoice.currency,
            vendor_match=vendor_match,
            line_match=line_match,
            evidence_refs=[item for item in (invoice.evidence_id,) if item],
            trace_id=trace_id or str(uuid4()),
            amount_tolerance=str(tolerance if tolerance is not None else EXACT_CENT),
        )

    def _persist(self, invoice: InvoiceRecord, result: InvoiceMatchResultRecord) -> None:
        status = "MATCHED" if result.matched else "MISMATCH"
        if "INVOICE_TOTAL_INVALID" in result.discrepancy_codes and not result.matched:
            status = "MISMATCH"
        updated = invoice.model_copy(
            update={"status": status, "match_result": result.model_dump(mode="json")}
        )
        self._repo.update_invoice(updated)
        logger.info(
            "invoice match audit tenant=%s invoice=%s po=%s process=%s step=%s status=%s codes=%s trace=%s",
            invoice.tenant_id,
            invoice.invoice_id,
            invoice.purchase_order_id,
            invoice.process_id,
            invoice.workflow_step_id,
            result.status,
            result.discrepancy_codes,
            result.trace_id,
        )
