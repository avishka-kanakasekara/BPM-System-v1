"""Deterministic invoice matching for the INVOICE_MATCHING stage.

Compares operator-supplied invoice evidence against expected purchase data
already stored on the process (metadata_json / process_json / execution
receipts) or explicitly provided as expected_* fields.

Does not invent OCR. Does not complete the process without a real match.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any


MATCHED = "MATCHED"
MISMATCH = "MISMATCH"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

_AMOUNT_TOLERANCE = Decimal("0.01")


def _norm_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text.lower() if text else None


def _norm_amount(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _pick(mapping: dict[str, Any] | None, *keys: str) -> Any:
    if not mapping:
        return None
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            value = mapping[key]
            # Nested dicts are handled as separate candidates; skip them here.
            if isinstance(value, (dict, list)):
                continue
            return value
    return None


@dataclass
class InvoiceEvidence:
    invoice_number: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    vendor: str | None = None
    po_reference: str | None = None
    notes: str = ""


@dataclass
class ExpectedPurchase:
    po_reference: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    vendor: str | None = None
    invoice_number: str | None = None


@dataclass
class InvoiceMatchResult:
    status: str
    message: str
    compared_fields: dict[str, Any] = field(default_factory=dict)
    mismatches: list[str] = field(default_factory=list)

    @property
    def matched(self) -> bool:
        return self.status == MATCHED


def extract_expected_from_process(
    *,
    metadata: dict[str, Any] | None,
    process_json: dict[str, Any] | None,
    receipt_results: list[dict[str, Any]] | None = None,
) -> ExpectedPurchase:
    """Pull expected purchase fields from known process storage locations only."""
    meta = metadata or {}
    payload = process_json or {}

    candidates: list[dict[str, Any]] = [meta, payload]
    for key in ("purchase", "purchase_order", "invoice", "expected_invoice", "po", "last_execution"):
        nested = payload.get(key) if isinstance(payload.get(key), dict) else None
        if nested:
            candidates.append(nested)
        nested_meta = meta.get(key) if isinstance(meta.get(key), dict) else None
        if nested_meta:
            candidates.append(nested_meta)

    # Agent 2 create_po_draft persists drafts as a list under po_drafts.
    for source in (meta, payload):
        drafts = source.get("po_drafts")
        if isinstance(drafts, list):
            for draft in reversed(drafts):
                if isinstance(draft, dict):
                    candidates.append(draft)

    for receipt in receipt_results or []:
        if isinstance(receipt, dict):
            candidates.append(receipt)
            result = receipt.get("result")
            if isinstance(result, dict):
                candidates.append(result)

    po = amount = currency = vendor = invoice_number = None
    for row in candidates:
        po = po or _pick(row, "po_reference", "po_number", "purchase_order", "po")
        amount = amount or _pick(row, "amount", "total", "purchase_amount", "po_amount")
        currency = currency or _pick(row, "currency", "currency_code")
        vendor = vendor or _pick(
            row, "vendor", "supplier", "vendor_name", "vendor_id"
        )
        invoice_number = invoice_number or _pick(
            row, "invoice_number", "expected_invoice_number", "invoice_id"
        )

    return ExpectedPurchase(
        po_reference=_norm_str(po),
        amount=_norm_amount(amount),
        currency=_norm_str(currency),
        vendor=_norm_str(vendor),
        invoice_number=_norm_str(invoice_number),
    )


def merge_expected(
    stored: ExpectedPurchase,
    *,
    expected_po_reference: str | None = None,
    expected_amount: float | None = None,
    expected_currency: str | None = None,
    expected_vendor: str | None = None,
    expected_invoice_number: str | None = None,
) -> ExpectedPurchase:
    """Request expected_* never invents values; it only fills gaps / overrides blanks."""
    return ExpectedPurchase(
        po_reference=_norm_str(expected_po_reference) or stored.po_reference,
        amount=_norm_amount(expected_amount) if expected_amount is not None else stored.amount,
        currency=_norm_str(expected_currency) or stored.currency,
        vendor=_norm_str(expected_vendor) or stored.vendor,
        invoice_number=_norm_str(expected_invoice_number) or stored.invoice_number,
    )


def match_invoice(invoice: InvoiceEvidence, expected: ExpectedPurchase) -> InvoiceMatchResult:
    """Compare provided invoice evidence to expected purchase data."""
    pairs: list[tuple[str, Any, Any]] = []
    if invoice.po_reference is not None and expected.po_reference is not None:
        pairs.append(("po_reference", _norm_str(invoice.po_reference), expected.po_reference))
    if invoice.amount is not None and expected.amount is not None:
        pairs.append(("amount", invoice.amount, expected.amount))
    if invoice.currency is not None and expected.currency is not None:
        pairs.append(("currency", _norm_str(invoice.currency), expected.currency))
    if invoice.vendor is not None and expected.vendor is not None:
        pairs.append(("vendor", _norm_str(invoice.vendor), expected.vendor))
    if invoice.invoice_number is not None and expected.invoice_number is not None:
        pairs.append(
            ("invoice_number", _norm_str(invoice.invoice_number), expected.invoice_number)
        )

    if not pairs:
        return InvoiceMatchResult(
            status=INSUFFICIENT_EVIDENCE,
            message=(
                "Invoice matching cannot complete: need at least one overlapping "
                "field between invoice evidence and expected purchase data "
                "(amount, PO reference, vendor, currency, or invoice number)."
            ),
            compared_fields={},
        )

    compared: dict[str, Any] = {}
    mismatches: list[str] = []
    for name, left, right in pairs:
        compared[name] = {"invoice": str(left), "expected": str(right)}
        if name == "amount":
            assert isinstance(left, Decimal) and isinstance(right, Decimal)
            if abs(left - right) > _AMOUNT_TOLERANCE:
                mismatches.append(
                    f"amount mismatch: invoice={left} expected={right}"
                )
        elif left != right:
            mismatches.append(f"{name} mismatch: invoice={left} expected={right}")

    if mismatches:
        return InvoiceMatchResult(
            status=MISMATCH,
            message="Invoice does not match expected purchase data.",
            compared_fields=compared,
            mismatches=mismatches,
        )

    return InvoiceMatchResult(
        status=MATCHED,
        message="Invoice matched expected purchase data.",
        compared_fields=compared,
    )
