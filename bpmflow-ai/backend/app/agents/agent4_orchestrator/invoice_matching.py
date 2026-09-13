"""Deterministic invoice matching for the INVOICE_MATCHING stage.

Performs a genuine three-way match: purchase order vs receipt/evidence vs invoice.
Tolerance is configurable from company policy (default 0.01).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

MATCHED = "MATCHED"
MISMATCH = "MISMATCH"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

DEFAULT_AMOUNT_TOLERANCE = Decimal("0.01")


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
class ReceiptEvidence:
    receipt_id: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    vendor: str | None = None
    po_reference: str | None = None
    receipt_status: str | None = None


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
    three_way: dict[str, Any] = field(default_factory=dict)

    @property
    def matched(self) -> bool:
        return self.status == MATCHED


def extract_expected_from_process(
    *,
    metadata: dict[str, Any] | None,
    process_json: dict[str, Any] | None,
    receipt_results: list[dict[str, Any]] | None = None,
) -> ExpectedPurchase:
    """Pull expected PO fields from known process storage locations only."""
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
        po = po or _pick(row, "po_reference", "po_number", "purchase_order", "po", "po_id")
        amount = amount or _pick(row, "amount", "total", "purchase_amount", "po_amount")
        currency = currency or _pick(row, "currency", "currency_code")
        vendor = vendor or _pick(row, "vendor", "supplier", "vendor_name", "vendor_id")
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


def extract_receipt_from_process(
    *,
    metadata: dict[str, Any] | None,
    process_json: dict[str, Any] | None,
    receipt_results: list[dict[str, Any]] | None = None,
) -> ReceiptEvidence:
    """Pull receipt / execution evidence for three-way matching."""
    meta = metadata or {}
    payload = process_json or {}
    candidates: list[dict[str, Any]] = []

    for source in (meta, payload):
        for key in ("last_execution", "execution_receipt", "receipt", "agent2_receipt"):
            nested = source.get(key)
            if isinstance(nested, dict):
                candidates.append(nested)

    for receipt in receipt_results or []:
        if isinstance(receipt, dict):
            candidates.append(receipt)
            result = receipt.get("result")
            if isinstance(result, dict):
                candidates.append(result)

    receipt_id = amount = currency = vendor = po_reference = status = None
    for row in candidates:
        receipt_id = receipt_id or _pick(row, "receipt_id", "id", "idempotency_key")
        amount = amount or _pick(row, "amount", "total", "purchase_amount")
        currency = currency or _pick(row, "currency", "currency_code")
        vendor = vendor or _pick(row, "vendor", "vendor_id", "supplier")
        po_reference = po_reference or _pick(row, "po_reference", "po_number", "po")
        status = status or _pick(row, "receipt_status", "status")

    return ReceiptEvidence(
        receipt_id=str(receipt_id) if receipt_id is not None else None,
        amount=_norm_amount(amount),
        currency=_norm_str(currency),
        vendor=_norm_str(vendor),
        po_reference=_norm_str(po_reference),
        receipt_status=str(status).upper() if status is not None else None,
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
    return ExpectedPurchase(
        po_reference=_norm_str(expected_po_reference) or stored.po_reference,
        amount=_norm_amount(expected_amount) if expected_amount is not None else stored.amount,
        currency=_norm_str(expected_currency) or stored.currency,
        vendor=_norm_str(expected_vendor) or stored.vendor,
        invoice_number=_norm_str(expected_invoice_number) or stored.invoice_number,
    )


def tolerance_from_policy_rules(rules: list[Any] | None) -> Decimal:
    """Read invoice amount tolerance from policy rule metadata."""
    for rule in rules or []:
        meta = getattr(rule, "metadata_json", None) or {}
        if isinstance(rule, dict):
            meta = rule.get("metadata_json") or {}
        raw = meta.get("invoice_amount_tolerance") or meta.get("amount_tolerance")
        if raw is not None:
            try:
                return Decimal(str(raw))
            except (InvalidOperation, ValueError, TypeError):
                continue
    return DEFAULT_AMOUNT_TOLERANCE


def three_way_match(
    *,
    po: ExpectedPurchase,
    receipt: ReceiptEvidence,
    invoice: InvoiceEvidence,
    amount_tolerance: Decimal | None = None,
) -> InvoiceMatchResult:
    """Compare PO, receipt, and invoice evidence with stated mismatch reasons."""
    tolerance = amount_tolerance if amount_tolerance is not None else DEFAULT_AMOUNT_TOLERANCE
    compared: dict[str, Any] = {}
    mismatches: list[str] = []

    if po.amount is None and receipt.amount is None:
        return InvoiceMatchResult(
            status=INSUFFICIENT_EVIDENCE,
            message=(
                "Three-way match cannot complete: purchase order and receipt amounts "
                "are both missing."
            ),
            three_way={"po": po.__dict__, "receipt": receipt.__dict__, "invoice": invoice.__dict__},
        )

    if invoice.amount is None:
        return InvoiceMatchResult(
            status=INSUFFICIENT_EVIDENCE,
            message="Three-way match cannot complete: invoice amount is missing.",
            three_way={"po": po.__dict__, "receipt": receipt.__dict__, "invoice": invoice.__dict__},
        )

    po_amount = po.amount
    receipt_amount = receipt.amount or po_amount
    invoice_amount = invoice.amount

    compared["amount"] = {
        "po": str(po_amount) if po_amount is not None else None,
        "receipt": str(receipt_amount) if receipt_amount is not None else None,
        "invoice": str(invoice_amount),
        "tolerance": str(tolerance),
    }

    if po_amount is not None and receipt_amount is not None:
        if abs(po_amount - receipt_amount) > tolerance:
            mismatches.append(
                f"PO vs receipt amount mismatch: po={po_amount} receipt={receipt_amount}"
            )

    if po_amount is not None and abs(po_amount - invoice_amount) > tolerance:
        mismatches.append(
            f"PO vs invoice amount mismatch: po={po_amount} invoice={invoice_amount}"
        )

    if receipt_amount is not None and abs(receipt_amount - invoice_amount) > tolerance:
        mismatches.append(
            f"Receipt vs invoice amount mismatch: receipt={receipt_amount} invoice={invoice_amount}"
        )

    invoice_po = _norm_str(invoice.po_reference) or receipt.po_reference
    invoice_vendor = _norm_str(invoice.vendor) or receipt.vendor
    invoice_currency = _norm_str(invoice.currency) or receipt.currency
    for label, left, right in (
        ("po_reference", po.po_reference, invoice_po),
        ("vendor", po.vendor, invoice_vendor),
        ("currency", po.currency, invoice_currency),
    ):
        if left is not None and right is not None:
            compared[label] = {"po_or_receipt": left, "invoice": right}
            if left != right:
                mismatches.append(f"{label} mismatch: expected={left} invoice={right}")

    if receipt.receipt_status and receipt.receipt_status not in {"SUCCESS", "MATCHED"}:
        mismatches.append(
            f"receipt status mismatch: expected SUCCESS got {receipt.receipt_status}"
        )

    payload = {
        "po": {
            "po_reference": po.po_reference,
            "amount": str(po.amount) if po.amount is not None else None,
            "vendor": po.vendor,
            "currency": po.currency,
        },
        "receipt": {
            "receipt_id": receipt.receipt_id,
            "amount": str(receipt.amount) if receipt.amount is not None else None,
            "vendor": receipt.vendor,
            "status": receipt.receipt_status,
        },
        "invoice": {
            "invoice_number": invoice.invoice_number,
            "amount": str(invoice.amount) if invoice.amount is not None else None,
            "vendor": invoice.vendor,
        },
    }

    if mismatches:
        return InvoiceMatchResult(
            status=MISMATCH,
            message="Three-way invoice match failed: " + "; ".join(mismatches),
            compared_fields=compared,
            mismatches=mismatches,
            three_way=payload,
        )

    return InvoiceMatchResult(
        status=MATCHED,
        message="Three-way match succeeded across PO, receipt, and invoice.",
        compared_fields=compared,
        three_way=payload,
    )


def match_invoice(
    invoice: InvoiceEvidence,
    expected: ExpectedPurchase,
    *,
    amount_tolerance: Decimal | None = None,
) -> InvoiceMatchResult:
    """Legacy two-way compare; delegates to three-way when receipt is absent."""
    receipt = ReceiptEvidence(
        amount=expected.amount,
        currency=expected.currency,
        vendor=expected.vendor,
        po_reference=expected.po_reference,
        receipt_status="SUCCESS",
    )
    return three_way_match(
        po=expected,
        receipt=receipt,
        invoice=invoice,
        amount_tolerance=amount_tolerance,
    )
