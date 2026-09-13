"""Invoice matching tests. Authoritative source is invoices + purchase_orders."""

from uuid import uuid4

from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID
from app.tests.test_phase8c_invoice_matching import _invoice, _po
from app.procurement.service import get_procurement


def test_match_requires_persisted_invoice() -> None:
    process_id = uuid4()
    po = _po(process_id=process_id)
    invoices = get_procurement().list_invoices(
        tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
    )
    assert invoices == []
    assert po.purchase_order_id is not None


def test_match_amount_and_po() -> None:
    process_id = uuid4()
    po = _po(process_id=process_id)
    invoice = _invoice(process_id=process_id, po_id=po.purchase_order_id, number="INV-UNIT-OK")
    result = get_procurement().match_invoice(
        tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
    )
    assert result.matched is True
    assert result.status == "MATCHED"


def test_mismatch_amount() -> None:
    process_id = uuid4()
    po = _po(process_id=process_id)
    invoice = _invoice(
        process_id=process_id,
        po_id=po.purchase_order_id,
        number="INV-UNIT-AMT",
        total="1600000",
        subtotal="1600000",
        qty="20",
        unit="80000",
    )
    result = get_procurement().match_invoice(
        tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
    )
    assert result.matched is False
    assert "AMOUNT_MISMATCH" in result.discrepancy_codes
