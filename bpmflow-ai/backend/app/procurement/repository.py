"""Tenant-scoped procurement store. All operations require tenant_id."""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from .exceptions import CrossTenantProcurementError, DuplicatePurchaseOrderError, VendorNotFoundError
from .schemas import (
    CreatePurchaseOrderInput,
    CreateQuotationInput,
    CreateVendorContactInput,
    CreateVendorInput,
    InvoiceItemRecord,
    InvoiceRecord,
    LineItemInput,
    PurchaseOrderItemRecord,
    PurchaseOrderRecord,
    QuotationItemRecord,
    QuotationRecord,
    VendorContactRecord,
    VendorRecord,
)


class ProcurementRepository(Protocol):
    def create_vendor(self, payload: CreateVendorInput) -> VendorRecord: ...
    def create_vendor_contact(self, payload: CreateVendorContactInput) -> VendorContactRecord: ...
    def get_vendor(self, *, tenant_id: UUID, vendor_id: UUID) -> VendorRecord | None: ...
    def get_vendor_by_code(self, *, tenant_id: UUID, vendor_code: str) -> VendorRecord | None: ...
    def list_vendors(self, *, tenant_id: UUID) -> list[VendorRecord]: ...
    def list_vendor_contacts(self, *, tenant_id: UUID, vendor_id: UUID) -> list[VendorContactRecord]: ...
    def create_quotation(self, payload: CreateQuotationInput) -> QuotationRecord: ...
    def get_quotation(self, *, tenant_id: UUID, quotation_id: UUID) -> QuotationRecord | None: ...
    def list_quotations_for_process(self, *, tenant_id: UUID, process_id: UUID) -> list[QuotationRecord]: ...
    def count_quotations_for_process(self, *, tenant_id: UUID, process_id: UUID) -> int: ...
    def create_purchase_order(self, record: PurchaseOrderRecord) -> PurchaseOrderRecord: ...
    def get_purchase_order(self, *, tenant_id: UUID, purchase_order_id: UUID) -> PurchaseOrderRecord | None: ...
    def get_purchase_order_by_step(
        self, *, tenant_id: UUID, workflow_step_id: UUID
    ) -> PurchaseOrderRecord | None: ...
    def list_purchase_orders_for_process(
        self, *, tenant_id: UUID, process_id: UUID
    ) -> list[PurchaseOrderRecord]: ...
    def next_po_number(self, *, tenant_id: UUID) -> str: ...
    def create_invoice(self, record: InvoiceRecord) -> InvoiceRecord: ...
    def get_invoice(self, *, tenant_id: UUID, invoice_id: UUID) -> InvoiceRecord | None: ...
    def find_invoice_by_id(self, invoice_id: UUID) -> InvoiceRecord | None: ...
    def list_invoices_for_process(self, *, tenant_id: UUID, process_id: UUID) -> list[InvoiceRecord]: ...
    def update_invoice(self, record: InvoiceRecord) -> InvoiceRecord: ...
    def clear(self) -> None: ...


def _money(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value)).quantize(Decimal("0.01"))


class InMemoryProcurementRepository:
    """Isolated tenant-keyed store used by tests. Never a production fallback."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._vendors: dict[tuple[UUID, UUID], VendorRecord] = {}
        self._contacts: dict[tuple[UUID, UUID], VendorContactRecord] = {}
        self._quotations: dict[tuple[UUID, UUID], QuotationRecord] = {}
        self._orders: dict[tuple[UUID, UUID], PurchaseOrderRecord] = {}
        self._invoices: dict[tuple[UUID, UUID], InvoiceRecord] = {}
        self._sequences: dict[UUID, int] = {}

    def clear(self) -> None:
        with self._lock:
            self._vendors.clear()
            self._contacts.clear()
            self._quotations.clear()
            self._orders.clear()
            self._invoices.clear()
            self._sequences.clear()

    def create_vendor(self, payload: CreateVendorInput) -> VendorRecord:
        with self._lock:
            if self.get_vendor_by_code(tenant_id=payload.tenant_id, vendor_code=payload.vendor_code):
                raise CrossTenantProcurementError(
                    "vendor_code already exists in tenant",
                    error_code="VENDOR_CODE_CONFLICT",
                )
            vendor_id = payload.vendor_id or uuid4()
            record = VendorRecord(
                vendor_id=vendor_id,
                tenant_id=payload.tenant_id,
                vendor_code=payload.vendor_code.strip(),
                legal_name=payload.legal_name.strip(),
                status=payload.status,
                phone=payload.phone,
                website=payload.website,
                notes=payload.notes,
            )
            self._vendors[(payload.tenant_id, vendor_id)] = record
            return record

    def create_vendor_contact(self, payload: CreateVendorContactInput) -> VendorContactRecord:
        vendor = self.get_vendor(tenant_id=payload.tenant_id, vendor_id=payload.vendor_id)
        if vendor is None:
            raise VendorNotFoundError("Vendor not found in tenant")
        contact_id = payload.contact_id or uuid4()
        record = VendorContactRecord(
            contact_id=contact_id,
            tenant_id=payload.tenant_id,
            vendor_id=payload.vendor_id,
            full_name=payload.full_name.strip(),
            email=(payload.email or "").strip().lower() or None,
            phone=payload.phone,
            title=payload.title,
            is_active=payload.is_active,
        )
        self._contacts[(payload.tenant_id, contact_id)] = record
        return record

    def get_vendor(self, *, tenant_id: UUID, vendor_id: UUID) -> VendorRecord | None:
        return self._vendors.get((tenant_id, vendor_id))

    def get_vendor_by_code(self, *, tenant_id: UUID, vendor_code: str) -> VendorRecord | None:
        code = (vendor_code or "").strip()
        for key, row in self._vendors.items():
            if key[0] == tenant_id and row.vendor_code == code:
                return row
        lowered = code.lower()
        for key, row in self._vendors.items():
            if key[0] == tenant_id and row.vendor_code.lower() == lowered:
                return row
        return None

    def list_vendors(self, *, tenant_id: UUID) -> list[VendorRecord]:
        return [row for key, row in self._vendors.items() if key[0] == tenant_id]

    def list_vendor_contacts(self, *, tenant_id: UUID, vendor_id: UUID) -> list[VendorContactRecord]:
        vendor = self.get_vendor(tenant_id=tenant_id, vendor_id=vendor_id)
        if vendor is None:
            return []
        return [
            row
            for key, row in self._contacts.items()
            if key[0] == tenant_id and row.vendor_id == vendor_id
        ]

    def create_quotation(self, payload: CreateQuotationInput) -> QuotationRecord:
        vendor = self.get_vendor(tenant_id=payload.tenant_id, vendor_id=payload.vendor_id)
        if vendor is None:
            raise VendorNotFoundError("Vendor not found in tenant")
        quotation_id = payload.quotation_id or uuid4()
        items = self._quotation_items(payload, quotation_id)
        subtotal = payload.subtotal if payload.subtotal is not None else sum(
            (item.line_total for item in items), Decimal("0")
        )
        total = payload.total if payload.total is not None else subtotal + _money(payload.tax)
        record = QuotationRecord(
            quotation_id=quotation_id,
            tenant_id=payload.tenant_id,
            quotation_number=payload.quotation_number or f"QT-{quotation_id.hex[:8].upper()}",
            vendor_id=payload.vendor_id,
            process_id=payload.process_id,
            currency=payload.currency.strip().upper(),
            subtotal=_money(subtotal),
            tax=_money(payload.tax),
            total=_money(total),
            status=payload.status,
            quotation_date=date.today(),
            evidence_id=payload.evidence_id,
            items=items,
        )
        self._quotations[(payload.tenant_id, quotation_id)] = record
        return record

    def get_quotation(self, *, tenant_id: UUID, quotation_id: UUID) -> QuotationRecord | None:
        return self._quotations.get((tenant_id, quotation_id))

    def list_quotations_for_process(self, *, tenant_id: UUID, process_id: UUID) -> list[QuotationRecord]:
        return [
            row
            for key, row in self._quotations.items()
            if key[0] == tenant_id and row.process_id == process_id
        ]

    def count_quotations_for_process(self, *, tenant_id: UUID, process_id: UUID) -> int:
        return len(self.list_quotations_for_process(tenant_id=tenant_id, process_id=process_id))

    def create_purchase_order(self, record: PurchaseOrderRecord) -> PurchaseOrderRecord:
        with self._lock:
            vendor = self.get_vendor(tenant_id=record.tenant_id, vendor_id=record.vendor_id)
            if vendor is None:
                raise VendorNotFoundError("Vendor not found in tenant")
            if record.workflow_step_id is not None:
                existing = self.get_purchase_order_by_step(
                    tenant_id=record.tenant_id, workflow_step_id=record.workflow_step_id
                )
                if existing is not None:
                    raise DuplicatePurchaseOrderError(
                        "A purchase order already exists for this workflow step"
                    )
            stored = record.model_copy(deep=True)
            if stored.created_at is None:
                stored = stored.model_copy(update={"created_at": datetime.now(UTC)})
            self._orders[(stored.tenant_id, stored.purchase_order_id)] = stored
            return stored

    def get_purchase_order(
        self, *, tenant_id: UUID, purchase_order_id: UUID
    ) -> PurchaseOrderRecord | None:
        return self._orders.get((tenant_id, purchase_order_id))

    def get_purchase_order_by_step(
        self, *, tenant_id: UUID, workflow_step_id: UUID
    ) -> PurchaseOrderRecord | None:
        for key, row in self._orders.items():
            if key[0] == tenant_id and row.workflow_step_id == workflow_step_id:
                return row
        return None

    def list_purchase_orders_for_process(
        self, *, tenant_id: UUID, process_id: UUID
    ) -> list[PurchaseOrderRecord]:
        return [
            row
            for key, row in self._orders.items()
            if key[0] == tenant_id and row.process_id == process_id
        ]

    def next_po_number(self, *, tenant_id: UUID) -> str:
        with self._lock:
            current = self._sequences.get(tenant_id, 1)
            self._sequences[tenant_id] = current + 1
            year = datetime.now(UTC).year
            return f"PO-{year}-{current:04d}"

    def create_invoice(self, record: InvoiceRecord) -> InvoiceRecord:
        with self._lock:
            po = self.get_purchase_order(
                tenant_id=record.tenant_id, purchase_order_id=record.purchase_order_id
            )
            if po is None:
                from .exceptions import PurchaseOrderNotFoundError

                raise PurchaseOrderNotFoundError("Purchase order not found in tenant")
            stored = record.model_copy(deep=True)
            if stored.received_at is None:
                stored = stored.model_copy(update={"received_at": datetime.now(UTC)})
            self._invoices[(stored.tenant_id, stored.invoice_id)] = stored
            return stored

    def get_invoice(self, *, tenant_id: UUID, invoice_id: UUID) -> InvoiceRecord | None:
        return self._invoices.get((tenant_id, invoice_id))

    def find_invoice_by_id(self, invoice_id: UUID) -> InvoiceRecord | None:
        for record in self._invoices.values():
            if record.invoice_id == invoice_id:
                return record
        return None

    def list_invoices_for_process(self, *, tenant_id: UUID, process_id: UUID) -> list[InvoiceRecord]:
        return [
            row
            for key, row in self._invoices.items()
            if key[0] == tenant_id and row.process_id == process_id
        ]

    def update_invoice(self, record: InvoiceRecord) -> InvoiceRecord:
        with self._lock:
            existing = self._invoices.get((record.tenant_id, record.invoice_id))
            if existing is None:
                from .exceptions import InvoiceNotFoundError

                raise InvoiceNotFoundError("Invoice not found in tenant")
            stored = record.model_copy(deep=True)
            self._invoices[(stored.tenant_id, stored.invoice_id)] = stored
            return stored

    def _quotation_items(
        self, payload: CreateQuotationInput, quotation_id: UUID
    ) -> list[QuotationItemRecord]:
        items: list[QuotationItemRecord] = []
        for line in payload.items:
            qty = Decimal(str(line.quantity))
            price = _money(line.unit_price)
            items.append(
                QuotationItemRecord(
                    tenant_id=payload.tenant_id,
                    quotation_id=quotation_id,
                    description=line.description,
                    quantity=qty,
                    unit_price=price,
                    line_total=_money(qty * price),
                )
            )
        return items
