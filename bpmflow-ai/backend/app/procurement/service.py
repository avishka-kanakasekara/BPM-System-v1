"""Tenant-scoped procurement service. Agents consume this, not metadata_json."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from app.core.logging import get_logger
from app.process_context.schemas import ProcessContext, QuotationFact

from .exceptions import (
    CrossTenantProcurementError,
    InsufficientBudgetError,
    MissingQuotationEvidenceError,
    ProcurementError,
    ProcurementUnavailableError,
    PurchaseOrderNotFoundError,
    VendorNotFoundError,
)
from .matching import InvoiceMatchingService
from .schemas import (
    CreateInvoiceInput,
    CreatePurchaseOrderInput,
    CreateQuotationInput,
    CreateVendorContactInput,
    CreateVendorInput,
    InvoiceItemRecord,
    InvoiceMatchResultRecord,
    InvoiceRecord,
    LineItemInput,
    PurchaseOrderItemRecord,
    PurchaseOrderRecord,
    QuotationRecord,
    VendorContactRecord,
    VendorRecord,
)
from .repository import InMemoryProcurementRepository, ProcurementRepository

_DEFAULT_REPO: ProcurementRepository | None = None
_DEFAULT_SERVICE: ProcurementService | None = None
logger = get_logger(__name__)


def _money(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value)).quantize(Decimal("0.01"))


class ProcurementService:
    """Authoritative vendors, quotations, and purchase orders."""

    def __init__(self, repository: ProcurementRepository) -> None:
        self._repo = repository

    @property
    def repository(self) -> ProcurementRepository:
        return self._repo

    def create_vendor(self, payload: CreateVendorInput) -> VendorRecord:
        return self._repo.create_vendor(payload)

    def create_vendor_contact(self, payload: CreateVendorContactInput) -> VendorContactRecord:
        return self._repo.create_vendor_contact(payload)

    def list_vendors(self, *, tenant_id: UUID) -> list[VendorRecord]:
        return self._repo.list_vendors(tenant_id=tenant_id)

    def get_vendor(self, *, tenant_id: UUID, vendor_id: UUID) -> VendorRecord | None:
        return self._repo.get_vendor(tenant_id=tenant_id, vendor_id=vendor_id)

    def list_vendor_contacts(self, *, tenant_id: UUID, vendor_id: UUID) -> list[VendorContactRecord]:
        return self._repo.list_vendor_contacts(tenant_id=tenant_id, vendor_id=vendor_id)

    def resolve_vendor(self, *, tenant_id: UUID, vendor_ref: str) -> VendorRecord:
        text = (vendor_ref or "").strip()
        if not text:
            raise VendorNotFoundError("Vendor identity is missing")
        try:
            vendor_uuid = UUID(text)
        except (TypeError, ValueError):
            vendor_uuid = None
        if vendor_uuid is not None:
            found = self._repo.get_vendor(tenant_id=tenant_id, vendor_id=vendor_uuid)
            if found is not None:
                return found
        found = self._repo.get_vendor_by_code(tenant_id=tenant_id, vendor_code=text)
        if found is not None:
            return found
        lowered = text.lower()
        for vendor in self._repo.list_vendors(tenant_id=tenant_id):
            if vendor.legal_name.strip().lower() == lowered:
                return vendor
        raise VendorNotFoundError(f"Vendor '{text}' was not found in tenant")

    def create_quotation(self, payload: CreateQuotationInput) -> QuotationRecord:
        return self._repo.create_quotation(payload)

    def list_quotations(self, *, tenant_id: UUID, process_id: UUID) -> list[QuotationRecord]:
        return self._repo.list_quotations_for_process(tenant_id=tenant_id, process_id=process_id)

    def count_quotations(self, *, tenant_id: UUID, process_id: UUID) -> int:
        return self._repo.count_quotations_for_process(tenant_id=tenant_id, process_id=process_id)

    def get_purchase_order_for_process(
        self, *, tenant_id: UUID, process_id: UUID
    ) -> PurchaseOrderRecord | None:
        rows = self._repo.list_purchase_orders_for_process(tenant_id=tenant_id, process_id=process_id)
        return rows[0] if rows else None

    def get_purchase_order_by_step(
        self, *, tenant_id: UUID, workflow_step_id: UUID
    ) -> PurchaseOrderRecord | None:
        return self._repo.get_purchase_order_by_step(
            tenant_id=tenant_id, workflow_step_id=workflow_step_id
        )

    def persist_quotations_from_context(
        self,
        *,
        tenant_id: UUID,
        process_id: UUID,
        facts: list[QuotationFact],
        default_vendor: VendorRecord,
        currency: str,
    ) -> list[QuotationRecord]:
        existing = self.list_quotations(tenant_id=tenant_id, process_id=process_id)
        if existing:
            return existing
        created: list[QuotationRecord] = []
        for index, fact in enumerate(facts, start=1):
            vendor = default_vendor
            if fact.vendor:
                try:
                    vendor = self.resolve_vendor(tenant_id=tenant_id, vendor_ref=str(fact.vendor))
                except VendorNotFoundError:
                    vendor = default_vendor
            amount = _money(fact.amount)
            quote_currency = (fact.currency or currency or "").strip().upper()
            created.append(
                self.create_quotation(
                    CreateQuotationInput(
                        tenant_id=tenant_id,
                        vendor_id=vendor.vendor_id,
                        process_id=process_id,
                        currency=quote_currency,
                        quotation_number=str(fact.quotation_id or f"QT-{index:04d}"),
                        total=amount,
                        subtotal=amount,
                        evidence_id=fact.evidence_id,
                        status="RECEIVED",
                    )
                )
            )
        return created

    def create_purchase_order(self, payload: CreatePurchaseOrderInput) -> PurchaseOrderRecord:
        currency = (payload.currency or "").strip().upper()
        if len(currency) < 3:
            raise ProcurementError(
                "Purchase currency is required",
                error_code="MISSING_REQUIRED_EXECUTION_CONTEXT",
            )
        amount = _money(payload.amount)
        if amount <= 0:
            raise ProcurementError("Purchase amount must be greater than zero", error_code="INVALID_AMOUNT")
        vendor = self.resolve_vendor(tenant_id=payload.tenant_id, vendor_ref=payload.vendor_ref)
        if payload.budget_available is not None and amount > _money(payload.budget_available):
            raise InsufficientBudgetError("Purchase amount exceeds available budget")
        if payload.workflow_step_id is not None:
            existing = self.get_purchase_order_by_step(
                tenant_id=payload.tenant_id, workflow_step_id=payload.workflow_step_id
            )
            if existing is not None:
                return existing
        facts = [QuotationFact.model_validate(item) if isinstance(item, dict) else item for item in payload.quotation_facts]
        if facts:
            self.persist_quotations_from_context(
                tenant_id=payload.tenant_id,
                process_id=payload.process_id,
                facts=facts,
                default_vendor=vendor,
                currency=currency,
            )
        quote_count = self.count_quotations(tenant_id=payload.tenant_id, process_id=payload.process_id)
        if payload.min_quotations and quote_count < payload.min_quotations:
            raise MissingQuotationEvidenceError(
                f"Policy requires {payload.min_quotations} quotation(s); process has {quote_count}"
            )
        quotations = self.list_quotations(tenant_id=payload.tenant_id, process_id=payload.process_id)
        selected = next((row for row in quotations if row.vendor_id == vendor.vendor_id), None)
        if selected is None and quotations:
            selected = quotations[0]
        items = self._po_items(payload, vendor_currency=currency, amount=amount)
        subtotal = sum((item.line_total for item in items), Decimal("0"))
        tax = _money(payload.tax)
        total = _money(subtotal + tax)
        po_id = uuid4()
        for item in items:
            item.purchase_order_id = po_id
            item.tenant_id = payload.tenant_id
        record = PurchaseOrderRecord(
            purchase_order_id=po_id,
            tenant_id=payload.tenant_id,
            po_number=self._repo.next_po_number(tenant_id=payload.tenant_id),
            process_id=payload.process_id,
            vendor_id=vendor.vendor_id,
            currency=currency,
            subtotal=_money(subtotal),
            tax=tax,
            total=total,
            status="DRAFT",
            workflow_plan_id=payload.workflow_plan_id,
            workflow_step_id=payload.workflow_step_id,
            created_by=payload.created_by,
            selected_quotation_id=None if selected is None else selected.quotation_id,
            notes=payload.notes,
            items=items,
        )
        return self._repo.create_purchase_order(record)

    def create_purchase_order_from_context(
        self,
        *,
        tenant_id: UUID,
        process_id: UUID,
        context: ProcessContext,
        workflow_plan_id: UUID | None = None,
        workflow_step_id: UUID | None = None,
        created_by: str | None = None,
        min_quotations: int = 0,
        notes: str | None = None,
    ) -> PurchaseOrderRecord:
        purchase = context.purchase
        if purchase.vendor_id in (None, ""):
            if purchase.vendor_name:
                vendor = self.resolve_vendor(tenant_id=tenant_id, vendor_ref=str(purchase.vendor_name))
            else:
                raise VendorNotFoundError("ProcessContext.purchase.vendor_id is missing")
        else:
            vendor = self.resolve_vendor(tenant_id=tenant_id, vendor_ref=str(purchase.vendor_id))
        if not (purchase.currency or "").strip():
            raise ProcurementError(
                "ProcessContext.purchase.currency is missing",
                error_code="MISSING_REQUIRED_EXECUTION_CONTEXT",
            )
        if purchase.amount is None:
            raise ProcurementError(
                "ProcessContext.purchase.amount is missing",
                error_code="MISSING_REQUIRED_EXECUTION_CONTEXT",
            )
        items = []
        for item in purchase.items or []:
            if not (item.description or item.quantity or item.unit_amount):
                continue
            qty = item.quantity or Decimal("1")
            unit = item.unit_amount
            if unit is None and purchase.amount is not None and qty:
                unit = (purchase.amount / qty).quantize(Decimal("0.01"))
            items.append(
                LineItemInput(
                    description=item.description or purchase.description or "Purchase request item",
                    quantity=qty,
                    unit_price=unit or purchase.amount,
                )
            )
        return self.create_purchase_order(
            CreatePurchaseOrderInput(
                tenant_id=tenant_id,
                process_id=process_id,
                vendor_ref=str(vendor.vendor_id),
                currency=str(purchase.currency),
                amount=purchase.amount,
                workflow_plan_id=workflow_plan_id,
                workflow_step_id=workflow_step_id,
                budget_available=context.budget.available_amount,
                min_quotations=min_quotations,
                notes=notes,
                created_by=created_by,
                items=items,
                quotation_facts=[fact.model_dump(mode="json") for fact in context.quotations],
            )
        )

    def create_invoice(self, payload: CreateInvoiceInput) -> InvoiceRecord:
        currency = (payload.currency or "").strip().upper()
        if len(currency) < 3:
            raise ProcurementError(
                "Invoice currency is required",
                error_code="MISSING_REQUIRED_EXECUTION_CONTEXT",
            )
        po = None
        if payload.purchase_order_id is not None:
            po = self._repo.get_purchase_order(
                tenant_id=payload.tenant_id, purchase_order_id=payload.purchase_order_id
            )
        if po is None:
            po = self.get_purchase_order_for_process(
                tenant_id=payload.tenant_id, process_id=payload.process_id
            )
        if po is None:
            raise PurchaseOrderNotFoundError("Purchase order not found for process")
        if po.tenant_id != payload.tenant_id or po.process_id != payload.process_id:
            raise CrossTenantProcurementError("Purchase order does not belong to this tenant/process")
        vendor = None
        if payload.vendor_ref:
            vendor = self.resolve_vendor(tenant_id=payload.tenant_id, vendor_ref=payload.vendor_ref)
        else:
            vendor = self.get_vendor(tenant_id=payload.tenant_id, vendor_id=po.vendor_id)
        if vendor is None:
            raise VendorNotFoundError("Invoice vendor could not be resolved")
        items: list[InvoiceItemRecord] = []
        invoice_id = payload.invoice_id or uuid4()
        for line in payload.items:
            qty = Decimal(str(line.quantity))
            price = _money(line.unit_price)
            items.append(
                InvoiceItemRecord(
                    tenant_id=payload.tenant_id,
                    invoice_id=invoice_id,
                    description=line.description,
                    quantity=qty,
                    unit_price=price,
                    line_total=_money(qty * price),
                    purchase_order_item_id=line.purchase_order_item_id,
                )
            )
        subtotal = payload.subtotal
        if subtotal is None:
            subtotal = sum((item.line_total for item in items), Decimal("0")) if items else payload.total
        if subtotal is None:
            raise ProcurementError("Invoice total is required", error_code="INVOICE_TOTAL_INVALID")
        tax = _money(payload.tax)
        total = payload.total if payload.total is not None else _money(subtotal) + tax
        record = InvoiceRecord(
            invoice_id=invoice_id,
            tenant_id=payload.tenant_id,
            invoice_number=payload.invoice_number.strip(),
            vendor_id=vendor.vendor_id,
            purchase_order_id=po.purchase_order_id,
            process_id=payload.process_id,
            currency=currency,
            subtotal=_money(subtotal),
            tax=tax,
            total=_money(total),
            status="RECEIVED",
            evidence_id=payload.evidence_id,
            items=items,
        )
        return self._repo.create_invoice(record)

    def list_invoices(self, *, tenant_id: UUID, process_id: UUID) -> list[InvoiceRecord]:
        return self._repo.list_invoices_for_process(tenant_id=tenant_id, process_id=process_id)

    def get_invoice(self, *, tenant_id: UUID, invoice_id: UUID) -> InvoiceRecord | None:
        return self._repo.get_invoice(tenant_id=tenant_id, invoice_id=invoice_id)

    def match_invoice(
        self,
        *,
        tenant_id: UUID,
        invoice_id: UUID,
        amount_tolerance: Decimal | None = None,
        trace_id: str | None = None,
    ) -> InvoiceMatchResultRecord:
        return InvoiceMatchingService(self._repo).match(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            amount_tolerance=amount_tolerance,
            trace_id=trace_id,
        )

    def _po_items(
        self,
        payload: CreatePurchaseOrderInput,
        *,
        vendor_currency: str,
        amount: Decimal,
    ) -> list[PurchaseOrderItemRecord]:
        if payload.items:
            rows = []
            for line in payload.items:
                qty = Decimal(str(line.quantity))
                price = _money(line.unit_price)
                rows.append(
                    PurchaseOrderItemRecord(
                        tenant_id=payload.tenant_id,
                        purchase_order_id=uuid4(),
                        description=line.description,
                        quantity=qty,
                        unit_price=price,
                        line_total=_money(qty * price),
                    )
                )
            return rows
        return [
            PurchaseOrderItemRecord(
                tenant_id=payload.tenant_id,
                purchase_order_id=uuid4(),
                description="Purchase request",
                quantity=Decimal("1"),
                unit_price=amount,
                line_total=amount,
            )
        ]


def _open_runtime_repository() -> ProcurementRepository:
    from app.core.database import get_sync_session_factory
    from app.core.persistence import PersistenceMode, get_effective_mode
    from app.core.supabase_rest import use_supabase_rest_fallback

    from .db_repository import RestProcurementRepository, SqlAlchemyProcurementRepository

    mode = get_effective_mode()
    if mode == PersistenceMode.POSTGRES:
        factory = get_sync_session_factory()
        if factory is None:
            raise ProcurementUnavailableError("Procurement database is unavailable")
        return SqlAlchemyProcurementRepository(factory)
    if use_supabase_rest_fallback():
        return RestProcurementRepository()
    raise ProcurementUnavailableError("Procurement database is unavailable")


def get_procurement() -> ProcurementService:
    global _DEFAULT_REPO, _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is not None:
        return _DEFAULT_SERVICE
    _DEFAULT_REPO = _open_runtime_repository()
    _DEFAULT_SERVICE = ProcurementService(_DEFAULT_REPO)
    return _DEFAULT_SERVICE


def reset_procurement() -> ProcurementService:
    """Test/dev fixture: isolated in-memory procurement. Never a production fallback."""
    global _DEFAULT_REPO, _DEFAULT_SERVICE
    _DEFAULT_REPO = InMemoryProcurementRepository()
    _DEFAULT_SERVICE = ProcurementService(_DEFAULT_REPO)
    return _DEFAULT_SERVICE


def configure_procurement(repository: ProcurementRepository) -> ProcurementService:
    global _DEFAULT_REPO, _DEFAULT_SERVICE
    _DEFAULT_REPO = repository
    _DEFAULT_SERVICE = ProcurementService(repository)
    return _DEFAULT_SERVICE
