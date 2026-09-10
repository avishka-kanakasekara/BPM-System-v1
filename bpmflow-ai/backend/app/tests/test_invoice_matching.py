"""Unit tests for deterministic invoice matching."""

from decimal import Decimal

from app.agents.agent4_orchestrator.invoice_matching import (
    INSUFFICIENT_EVIDENCE,
    MATCHED,
    MISMATCH,
    InvoiceEvidence,
    ExpectedPurchase,
    match_invoice,
)


def test_match_requires_overlapping_fields() -> None:
    result = match_invoice(
        InvoiceEvidence(notes="only notes"),
        ExpectedPurchase(),
    )
    assert result.status == INSUFFICIENT_EVIDENCE
    assert result.matched is False


def test_match_amount_and_po() -> None:
    result = match_invoice(
        InvoiceEvidence(amount=Decimal("100.00"), po_reference="PO-1"),
        ExpectedPurchase(amount=Decimal("100.00"), po_reference="po-1"),
    )
    assert result.status == MATCHED


def test_mismatch_amount() -> None:
    result = match_invoice(
        InvoiceEvidence(amount=Decimal("99.00"), po_reference="PO-1"),
        ExpectedPurchase(amount=Decimal("100.00"), po_reference="PO-1"),
    )
    assert result.status == MISMATCH
    assert result.mismatches


def test_extract_expected_from_po_drafts() -> None:
    from app.agents.agent4_orchestrator.invoice_matching import extract_expected_from_process

    expected = extract_expected_from_process(
        metadata={
            "po_drafts": [
                {
                    "po_number": "PO-2026-ABC123",
                    "vendor_id": "VENDOR-ACME",
                    "amount": 2500,
                    "currency": "USD",
                }
            ]
        },
        process_json={},
    )
    assert expected.po_reference == "po-2026-abc123"
    assert expected.amount == Decimal("2500.00")
    assert expected.vendor == "vendor-acme"
    assert expected.currency == "usd"


def test_extract_expected_from_purchase_order() -> None:
    from app.agents.agent4_orchestrator.invoice_matching import extract_expected_from_process

    expected = extract_expected_from_process(
        metadata={
            "purchase_order": {
                "po_reference": "PO-9",
                "amount": 99.5,
                "vendor": "Acme",
                "currency": "USD",
            }
        },
        process_json={},
    )
    assert expected.po_reference == "po-9"
    assert expected.amount == Decimal("99.50")
    assert expected.vendor == "acme"
