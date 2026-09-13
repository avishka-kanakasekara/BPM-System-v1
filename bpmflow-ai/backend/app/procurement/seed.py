"""Explicit demo procurement seed. Never runs automatically on request."""

from __future__ import annotations

from uuid import UUID

from .schemas import CreateVendorContactInput, CreateVendorInput
from .service import ProcurementService, get_procurement

BPMFLOW_DEMO_TENANT_ID = UUID("00000000-0000-0000-0000-00000000d001")

VENDOR_BPM_SUPPLIES = UUID("d0d00000-0000-4000-8000-000000000501")
VENDOR_TECHSOURCE = UUID("d0d00000-0000-4000-8000-000000000502")
VENDOR_OFFICE_SYSTEMS = UUID("d0d00000-0000-4000-8000-000000000503")

VENDOR_CODE_IT = "vendor-it-01"
VENDOR_CODE_BPM = "VENDOR-001"
VENDOR_CODE_TECH = "VENDOR-002"
VENDOR_CODE_OFFICE = "VENDOR-003"


def seed_bpmflow_demo_procurement(
    service: ProcurementService | None = None,
    *,
    tenant_id: UUID = BPMFLOW_DEMO_TENANT_ID,
) -> UUID:
    """Fictional demo vendors only. Call explicitly from tests or admin seed."""
    procurement = service or get_procurement()
    if procurement.get_vendor(tenant_id=tenant_id, vendor_id=VENDOR_BPM_SUPPLIES) is None:
        procurement.create_vendor(
            CreateVendorInput(
                tenant_id=tenant_id,
                vendor_id=VENDOR_BPM_SUPPLIES,
                vendor_code=VENDOR_CODE_IT,
                legal_name="BPM Supplies Ltd",
                notes="Demo/test seed vendor. Not production master data.",
            )
        )
        procurement.create_vendor_contact(
            CreateVendorContactInput(
                tenant_id=tenant_id,
                vendor_id=VENDOR_BPM_SUPPLIES,
                full_name="Priya Vendor",
                email="purchasing@bpm-supplies.example.com",
                title="Account Manager",
            )
        )
    if procurement.get_vendor(tenant_id=tenant_id, vendor_id=VENDOR_TECHSOURCE) is None:
        procurement.create_vendor(
            CreateVendorInput(
                tenant_id=tenant_id,
                vendor_id=VENDOR_TECHSOURCE,
                vendor_code=VENDOR_CODE_TECH,
                legal_name="TechSource Lanka",
                notes="Demo/test seed vendor. Not production master data.",
            )
        )
    if procurement.get_vendor(tenant_id=tenant_id, vendor_id=VENDOR_OFFICE_SYSTEMS) is None:
        procurement.create_vendor(
            CreateVendorInput(
                tenant_id=tenant_id,
                vendor_id=VENDOR_OFFICE_SYSTEMS,
                vendor_code=VENDOR_CODE_OFFICE,
                legal_name="Office Systems Lanka",
                notes="Demo/test seed vendor. Not production master data.",
            )
        )
    if procurement.repository.get_vendor_by_code(tenant_id=tenant_id, vendor_code=VENDOR_CODE_BPM) is None:
        procurement.create_vendor(
            CreateVendorInput(
                tenant_id=tenant_id,
                vendor_code=VENDOR_CODE_BPM,
                legal_name="BPM Supplies Ltd (code VENDOR-001)",
                notes="Demo/test seed. Same legal entity alias; unique tenant code.",
            )
        )
    return tenant_id


def seed_bpmflow_demo_invoices(
    service: ProcurementService | None = None,
    *,
    tenant_id: UUID = BPMFLOW_DEMO_TENANT_ID,
) -> dict[str, str]:
    """Explicit fictional invoices for tests/demo. Never called automatically."""
    from decimal import Decimal

    from .schemas import CreateInvoiceInput, CreatePurchaseOrderInput, LineItemInput

    procurement = service or get_procurement()
    seed_bpmflow_demo_procurement(procurement, tenant_id=tenant_id)
    scenarios = {
        "matched": "INV-DEMO-MATCHED",
        "amount_mismatch": "INV-DEMO-AMOUNT",
        "vendor_mismatch": "INV-DEMO-VENDOR",
        "currency_mismatch": "INV-DEMO-CURRENCY",
        "quantity_mismatch": "INV-DEMO-QTY",
    }
    matched_process = UUID("d0d00000-0000-4000-8000-000000000611")
    if procurement.list_invoices(tenant_id=tenant_id, process_id=matched_process):
        return scenarios
    laptop_20 = LineItemInput(description="Laptop", quantity=Decimal("20"), unit_price=Decimal("75000"))

    def _make_po(process_id: UUID, amount: str = "1500000"):
        return procurement.create_purchase_order(
            CreatePurchaseOrderInput(
                tenant_id=tenant_id,
                process_id=process_id,
                vendor_ref=VENDOR_CODE_IT,
                currency="LKR",
                amount=Decimal(amount),
                items=[laptop_20],
            )
        )

    po = _make_po(matched_process)
    procurement.create_invoice(
        CreateInvoiceInput(
            tenant_id=tenant_id,
            process_id=matched_process,
            purchase_order_id=po.purchase_order_id,
            vendor_ref=VENDOR_CODE_IT,
            invoice_number="INV-DEMO-MATCHED",
            currency="LKR",
            total=Decimal("1500000"),
            items=[laptop_20],
        )
    )
    scenarios["matched"] = "INV-DEMO-MATCHED"

    amount_process = UUID("d0d00000-0000-4000-8000-000000000612")
    po = _make_po(amount_process)
    procurement.create_invoice(
        CreateInvoiceInput(
            tenant_id=tenant_id,
            process_id=amount_process,
            purchase_order_id=po.purchase_order_id,
            vendor_ref=VENDOR_CODE_IT,
            invoice_number="INV-DEMO-AMOUNT",
            currency="LKR",
            subtotal=Decimal("1600000"),
            total=Decimal("1600000"),
            items=[LineItemInput(description="Laptop", quantity=Decimal("20"), unit_price=Decimal("80000"))],
        )
    )
    scenarios["amount_mismatch"] = "INV-DEMO-AMOUNT"

    vendor_process = UUID("d0d00000-0000-4000-8000-000000000613")
    po = _make_po(vendor_process)
    procurement.create_invoice(
        CreateInvoiceInput(
            tenant_id=tenant_id,
            process_id=vendor_process,
            purchase_order_id=po.purchase_order_id,
            vendor_ref=VENDOR_CODE_TECH,
            invoice_number="INV-DEMO-VENDOR",
            currency="LKR",
            total=Decimal("1500000"),
            items=[laptop_20],
        )
    )
    scenarios["vendor_mismatch"] = "INV-DEMO-VENDOR"

    currency_process = UUID("d0d00000-0000-4000-8000-000000000614")
    po = _make_po(currency_process)
    procurement.create_invoice(
        CreateInvoiceInput(
            tenant_id=tenant_id,
            process_id=currency_process,
            purchase_order_id=po.purchase_order_id,
            vendor_ref=VENDOR_CODE_IT,
            invoice_number="INV-DEMO-CURRENCY",
            currency="USD",
            total=Decimal("1500000"),
            items=[laptop_20],
        )
    )
    scenarios["currency_mismatch"] = "INV-DEMO-CURRENCY"

    qty_process = UUID("d0d00000-0000-4000-8000-000000000615")
    po = _make_po(qty_process)
    procurement.create_invoice(
        CreateInvoiceInput(
            tenant_id=tenant_id,
            process_id=qty_process,
            purchase_order_id=po.purchase_order_id,
            vendor_ref=VENDOR_CODE_IT,
            invoice_number="INV-DEMO-QTY",
            currency="LKR",
            subtotal=Decimal("1425000"),
            total=Decimal("1425000"),
            items=[LineItemInput(description="Laptop", quantity=Decimal("19"), unit_price=Decimal("75000"))],
        )
    )
    scenarios["quantity_mismatch"] = "INV-DEMO-QTY"
    return scenarios
