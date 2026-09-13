"""Tenant-scoped procurement persistence (SQLAlchemy + PostgREST)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import get_logger
from app.core.supabase_rest import rest_insert, rest_select

from .exceptions import (
    DuplicatePurchaseOrderError,
    ProcurementUnavailableError,
    VendorNotFoundError,
)
from .schemas import (
    CreateQuotationInput,
    CreateVendorContactInput,
    CreateVendorInput,
    InvoiceItemRecord,
    InvoiceRecord,
    PurchaseOrderItemRecord,
    PurchaseOrderRecord,
    QuotationItemRecord,
    QuotationRecord,
    VendorContactRecord,
    VendorRecord,
)

logger = get_logger(__name__)


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _as_uuid_opt(value: Any) -> UUID | None:
    if value in (None, ""):
        return None
    return _as_uuid(value)


def _money(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _bind(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _params(values: dict[str, Any]) -> dict[str, Any]:
    return {key: _bind(value) for key, value in values.items()}


def _unavailable(exc: Exception) -> ProcurementUnavailableError:
    error = ProcurementUnavailableError("Procurement database is unavailable")
    error.__cause__ = exc
    return error


def _vendor_from_row(row: dict[str, Any]) -> VendorRecord:
    return VendorRecord(
        vendor_id=_as_uuid(row["id"]),
        tenant_id=_as_uuid(row["tenant_id"]),
        vendor_code=row["vendor_code"],
        legal_name=row["legal_name"],
        status=row.get("status") or "active",
        phone=row.get("phone"),
        website=row.get("website"),
        notes=row.get("notes"),
    )


def _contact_from_row(row: dict[str, Any]) -> VendorContactRecord:
    return VendorContactRecord(
        contact_id=_as_uuid(row["id"]),
        tenant_id=_as_uuid(row["tenant_id"]),
        vendor_id=_as_uuid(row["vendor_id"]),
        full_name=row["full_name"],
        email=row.get("email"),
        phone=row.get("phone"),
        title=row.get("title"),
        is_active=bool(row.get("is_active", True)),
    )


def _quote_from_row(row: dict[str, Any], items: list[QuotationItemRecord] | None = None) -> QuotationRecord:
    qdate = row.get("quotation_date")
    return QuotationRecord(
        quotation_id=_as_uuid(row["id"]),
        tenant_id=_as_uuid(row["tenant_id"]),
        quotation_number=row["quotation_number"],
        vendor_id=_as_uuid(row["vendor_id"]),
        process_id=_as_uuid(row["process_id"]),
        currency=row["currency"],
        subtotal=_money(row.get("subtotal")),
        tax=_money(row.get("tax")),
        total=_money(row.get("total")),
        status=row.get("status") or "RECEIVED",
        quotation_date=qdate if isinstance(qdate, date) else None,
        evidence_id=row.get("evidence_id"),
        document_id=_as_uuid_opt(row.get("document_id")),
        workflow_step_id=_as_uuid_opt(row.get("workflow_step_id")),
        items=items or [],
    )


def _po_from_row(row: dict[str, Any], items: list[PurchaseOrderItemRecord] | None = None) -> PurchaseOrderRecord:
    return PurchaseOrderRecord(
        purchase_order_id=_as_uuid(row["id"]),
        tenant_id=_as_uuid(row["tenant_id"]),
        po_number=row["po_number"],
        process_id=_as_uuid(row["process_id"]),
        vendor_id=_as_uuid(row["vendor_id"]),
        currency=row["currency"],
        subtotal=_money(row.get("subtotal")),
        tax=_money(row.get("tax")),
        total=_money(row.get("total")),
        status=row.get("status") or "DRAFT",
        workflow_plan_id=_as_uuid_opt(row.get("workflow_plan_id")),
        workflow_step_id=_as_uuid_opt(row.get("workflow_step_id")),
        created_by=row.get("created_by"),
        selected_quotation_id=_as_uuid_opt(row.get("selected_quotation_id")),
        notes=row.get("notes"),
        items=items or [],
    )


class SqlAlchemyProcurementRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def _session(self) -> Session:
        return self._session_factory()

    def _exec(self, session: Session, statement, params: dict[str, Any]):
        return session.execute(statement, _params(params))

    def clear(self) -> None:
        return None

    def create_vendor(self, payload: CreateVendorInput) -> VendorRecord:
        vendor_id = payload.vendor_id or uuid4()
        try:
            with self._session() as session:
                self._exec(
                    session,
                    text(
                        """
                        INSERT INTO vendors (
                            id, tenant_id, vendor_code, legal_name, status, phone, website, notes
                        ) VALUES (
                            :id, :tenant_id, :vendor_code, :legal_name, :status, :phone, :website, :notes
                        )
                        """
                    ),
                    {
                        "id": vendor_id,
                        "tenant_id": payload.tenant_id,
                        "vendor_code": payload.vendor_code.strip(),
                        "legal_name": payload.legal_name.strip(),
                        "status": payload.status,
                        "phone": payload.phone,
                        "website": payload.website,
                        "notes": payload.notes,
                    },
                )
                session.commit()
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        found = self.get_vendor(tenant_id=payload.tenant_id, vendor_id=vendor_id)
        if found is None:
            raise ProcurementUnavailableError("Vendor insert did not persist")
        return found

    def create_vendor_contact(self, payload: CreateVendorContactInput) -> VendorContactRecord:
        if self.get_vendor(tenant_id=payload.tenant_id, vendor_id=payload.vendor_id) is None:
            raise VendorNotFoundError("Vendor not found in tenant")
        contact_id = payload.contact_id or uuid4()
        try:
            with self._session() as session:
                self._exec(
                    session,
                    text(
                        """
                        INSERT INTO vendor_contacts (
                            id, tenant_id, vendor_id, full_name, email, phone, title, is_active
                        ) VALUES (
                            :id, :tenant_id, :vendor_id, :full_name, :email, :phone, :title, :is_active
                        )
                        """
                    ),
                    {
                        "id": contact_id,
                        "tenant_id": payload.tenant_id,
                        "vendor_id": payload.vendor_id,
                        "full_name": payload.full_name,
                        "email": (payload.email or "").strip().lower() or None,
                        "phone": payload.phone,
                        "title": payload.title,
                        "is_active": payload.is_active,
                    },
                )
                session.commit()
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        contacts = self.list_vendor_contacts(tenant_id=payload.tenant_id, vendor_id=payload.vendor_id)
        return next(item for item in contacts if item.contact_id == contact_id)

    def get_vendor(self, *, tenant_id: UUID, vendor_id: UUID) -> VendorRecord | None:
        try:
            with self._session() as session:
                row = self._exec(
                    session,
                    text("SELECT * FROM vendors WHERE tenant_id = :tenant_id AND id = :id"),
                    {"tenant_id": tenant_id, "id": vendor_id},
                ).mappings().first()
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        return None if row is None else _vendor_from_row(dict(row))

    def get_vendor_by_code(self, *, tenant_id: UUID, vendor_code: str) -> VendorRecord | None:
        try:
            with self._session() as session:
                row = self._exec(
                    session,
                    text(
                        """
                        SELECT * FROM vendors
                        WHERE tenant_id = :tenant_id AND lower(vendor_code) = lower(:vendor_code)
                        """
                    ),
                    {"tenant_id": tenant_id, "vendor_code": vendor_code},
                ).mappings().first()
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        return None if row is None else _vendor_from_row(dict(row))

    def list_vendors(self, *, tenant_id: UUID) -> list[VendorRecord]:
        try:
            with self._session() as session:
                rows = self._exec(
                    session,
                    text("SELECT * FROM vendors WHERE tenant_id = :tenant_id ORDER BY vendor_code"),
                    {"tenant_id": tenant_id},
                ).mappings().all()
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        return [_vendor_from_row(dict(row)) for row in rows]

    def list_vendor_contacts(self, *, tenant_id: UUID, vendor_id: UUID) -> list[VendorContactRecord]:
        try:
            with self._session() as session:
                rows = self._exec(
                    session,
                    text(
                        """
                        SELECT * FROM vendor_contacts
                        WHERE tenant_id = :tenant_id AND vendor_id = :vendor_id
                        """
                    ),
                    {"tenant_id": tenant_id, "vendor_id": vendor_id},
                ).mappings().all()
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        return [_contact_from_row(dict(row)) for row in rows]

    def create_quotation(self, payload: CreateQuotationInput) -> QuotationRecord:
        if self.get_vendor(tenant_id=payload.tenant_id, vendor_id=payload.vendor_id) is None:
            raise VendorNotFoundError("Vendor not found in tenant")
        quotation_id = payload.quotation_id or uuid4()
        items = payload.items
        subtotal = payload.subtotal
        if subtotal is None:
            subtotal = sum(
                (Decimal(str(line.quantity)) * _money(line.unit_price) for line in items),
                Decimal("0"),
            )
        total = payload.total if payload.total is not None else _money(subtotal) + _money(payload.tax)
        try:
            with self._session() as session:
                self._exec(
                    session,
                    text(
                        """
                        INSERT INTO quotations (
                            id, tenant_id, quotation_number, vendor_id, process_id, quotation_date,
                            currency, subtotal, tax, total, status, evidence_id
                        ) VALUES (
                            :id, :tenant_id, :quotation_number, :vendor_id, :process_id, :quotation_date,
                            :currency, :subtotal, :tax, :total, :status, :evidence_id
                        )
                        """
                    ),
                    {
                        "id": quotation_id,
                        "tenant_id": payload.tenant_id,
                        "quotation_number": payload.quotation_number or f"QT-{quotation_id.hex[:8].upper()}",
                        "vendor_id": payload.vendor_id,
                        "process_id": payload.process_id,
                        "quotation_date": date.today(),
                        "currency": payload.currency.strip().upper(),
                        "subtotal": _money(subtotal),
                        "tax": _money(payload.tax),
                        "total": _money(total),
                        "status": payload.status,
                        "evidence_id": payload.evidence_id,
                    },
                )
                for line in items:
                    qty = Decimal(str(line.quantity))
                    price = _money(line.unit_price)
                    self._exec(
                        session,
                        text(
                            """
                            INSERT INTO quotation_items (
                                id, tenant_id, quotation_id, description, quantity, unit_price, line_total
                            ) VALUES (
                                :id, :tenant_id, :quotation_id, :description, :quantity, :unit_price, :line_total
                            )
                            """
                        ),
                        {
                            "id": uuid4(),
                            "tenant_id": payload.tenant_id,
                            "quotation_id": quotation_id,
                            "description": line.description,
                            "quantity": qty,
                            "unit_price": price,
                            "line_total": _money(qty * price),
                        },
                    )
                session.commit()
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        found = self.get_quotation(tenant_id=payload.tenant_id, quotation_id=quotation_id)
        if found is None:
            raise ProcurementUnavailableError("Quotation insert did not persist")
        return found

    def get_quotation(self, *, tenant_id: UUID, quotation_id: UUID) -> QuotationRecord | None:
        try:
            with self._session() as session:
                row = self._exec(
                    session,
                    text("SELECT * FROM quotations WHERE tenant_id = :tenant_id AND id = :id"),
                    {"tenant_id": tenant_id, "id": quotation_id},
                ).mappings().first()
                if row is None:
                    return None
                items = self._quote_items(session, tenant_id=tenant_id, quotation_id=quotation_id)
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        return _quote_from_row(dict(row), items)

    def list_quotations_for_process(self, *, tenant_id: UUID, process_id: UUID) -> list[QuotationRecord]:
        try:
            with self._session() as session:
                rows = self._exec(
                    session,
                    text(
                        """
                        SELECT * FROM quotations
                        WHERE tenant_id = :tenant_id AND process_id = :process_id
                        ORDER BY created_at
                        """
                    ),
                    {"tenant_id": tenant_id, "process_id": process_id},
                ).mappings().all()
                result = []
                for row in rows:
                    mapping = dict(row)
                    items = self._quote_items(
                        session, tenant_id=tenant_id, quotation_id=_as_uuid(mapping["id"])
                    )
                    result.append(_quote_from_row(mapping, items))
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        return result

    def count_quotations_for_process(self, *, tenant_id: UUID, process_id: UUID) -> int:
        try:
            with self._session() as session:
                value = self._exec(
                    session,
                    text(
                        """
                        SELECT COUNT(*) FROM quotations
                        WHERE tenant_id = :tenant_id AND process_id = :process_id
                        """
                    ),
                    {"tenant_id": tenant_id, "process_id": process_id},
                ).scalar()
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        return int(value or 0)

    def _quote_items(self, session: Session, *, tenant_id: UUID, quotation_id: UUID) -> list[QuotationItemRecord]:
        rows = self._exec(
            session,
            text(
                """
                SELECT * FROM quotation_items
                WHERE tenant_id = :tenant_id AND quotation_id = :quotation_id
                """
            ),
            {"tenant_id": tenant_id, "quotation_id": quotation_id},
        ).mappings().all()
        return [
            QuotationItemRecord(
                item_id=_as_uuid(row["id"]),
                tenant_id=_as_uuid(row["tenant_id"]),
                quotation_id=_as_uuid(row["quotation_id"]),
                description=row["description"],
                quantity=Decimal(str(row["quantity"])),
                unit_price=_money(row["unit_price"]),
                line_total=_money(row["line_total"]),
            )
            for row in rows
        ]

    def create_purchase_order(self, record: PurchaseOrderRecord) -> PurchaseOrderRecord:
        try:
            with self._session() as session:
                self._exec(
                    session,
                    text(
                        """
                        INSERT INTO purchase_orders (
                            id, tenant_id, po_number, process_id, vendor_id, workflow_plan_id,
                            workflow_step_id, currency, subtotal, tax, total, status, created_by,
                            selected_quotation_id, notes
                        ) VALUES (
                            :id, :tenant_id, :po_number, :process_id, :vendor_id, :workflow_plan_id,
                            :workflow_step_id, :currency, :subtotal, :tax, :total, :status, :created_by,
                            :selected_quotation_id, :notes
                        )
                        """
                    ),
                    {
                        "id": record.purchase_order_id,
                        "tenant_id": record.tenant_id,
                        "po_number": record.po_number,
                        "process_id": record.process_id,
                        "vendor_id": record.vendor_id,
                        "workflow_plan_id": record.workflow_plan_id,
                        "workflow_step_id": record.workflow_step_id,
                        "currency": record.currency,
                        "subtotal": record.subtotal,
                        "tax": record.tax,
                        "total": record.total,
                        "status": record.status,
                        "created_by": record.created_by,
                        "selected_quotation_id": record.selected_quotation_id,
                        "notes": record.notes,
                    },
                )
                for item in record.items:
                    self._exec(
                        session,
                        text(
                            """
                            INSERT INTO purchase_order_items (
                                id, tenant_id, purchase_order_id, description, quantity,
                                unit_price, line_total, source_quotation_item_id
                            ) VALUES (
                                :id, :tenant_id, :purchase_order_id, :description, :quantity,
                                :unit_price, :line_total, :source_quotation_item_id
                            )
                            """
                        ),
                        {
                            "id": item.item_id,
                            "tenant_id": record.tenant_id,
                            "purchase_order_id": record.purchase_order_id,
                            "description": item.description,
                            "quantity": item.quantity,
                            "unit_price": item.unit_price,
                            "line_total": item.line_total,
                            "source_quotation_item_id": item.source_quotation_item_id,
                        },
                    )
                session.commit()
        except IntegrityError as exc:
            raise DuplicatePurchaseOrderError("Purchase order uniqueness constraint failed") from exc
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        found = self.get_purchase_order(
            tenant_id=record.tenant_id, purchase_order_id=record.purchase_order_id
        )
        if found is None:
            raise ProcurementUnavailableError("Purchase order insert did not persist")
        return found

    def get_purchase_order(self, *, tenant_id: UUID, purchase_order_id: UUID) -> PurchaseOrderRecord | None:
        try:
            with self._session() as session:
                row = self._exec(
                    session,
                    text("SELECT * FROM purchase_orders WHERE tenant_id = :tenant_id AND id = :id"),
                    {"tenant_id": tenant_id, "id": purchase_order_id},
                ).mappings().first()
                if row is None:
                    return None
                items = self._po_items(session, tenant_id=tenant_id, purchase_order_id=purchase_order_id)
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        return _po_from_row(dict(row), items)

    def get_purchase_order_by_step(
        self, *, tenant_id: UUID, workflow_step_id: UUID
    ) -> PurchaseOrderRecord | None:
        try:
            with self._session() as session:
                row = self._exec(
                    session,
                    text(
                        """
                        SELECT * FROM purchase_orders
                        WHERE tenant_id = :tenant_id AND workflow_step_id = :workflow_step_id
                        """
                    ),
                    {"tenant_id": tenant_id, "workflow_step_id": workflow_step_id},
                ).mappings().first()
                if row is None:
                    return None
                mapping = dict(row)
                items = self._po_items(
                    session, tenant_id=tenant_id, purchase_order_id=_as_uuid(mapping["id"])
                )
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        return _po_from_row(mapping, items)

    def list_purchase_orders_for_process(
        self, *, tenant_id: UUID, process_id: UUID
    ) -> list[PurchaseOrderRecord]:
        try:
            with self._session() as session:
                rows = self._exec(
                    session,
                    text(
                        """
                        SELECT * FROM purchase_orders
                        WHERE tenant_id = :tenant_id AND process_id = :process_id
                        ORDER BY created_at
                        """
                    ),
                    {"tenant_id": tenant_id, "process_id": process_id},
                ).mappings().all()
                result = []
                for row in rows:
                    mapping = dict(row)
                    items = self._po_items(
                        session, tenant_id=tenant_id, purchase_order_id=_as_uuid(mapping["id"])
                    )
                    result.append(_po_from_row(mapping, items))
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        return result

    def _po_items(
        self, session: Session, *, tenant_id: UUID, purchase_order_id: UUID
    ) -> list[PurchaseOrderItemRecord]:
        rows = self._exec(
            session,
            text(
                """
                SELECT * FROM purchase_order_items
                WHERE tenant_id = :tenant_id AND purchase_order_id = :purchase_order_id
                """
            ),
            {"tenant_id": tenant_id, "purchase_order_id": purchase_order_id},
        ).mappings().all()
        return [
            PurchaseOrderItemRecord(
                item_id=_as_uuid(row["id"]),
                tenant_id=_as_uuid(row["tenant_id"]),
                purchase_order_id=_as_uuid(row["purchase_order_id"]),
                description=row["description"],
                quantity=Decimal(str(row["quantity"])),
                unit_price=_money(row["unit_price"]),
                line_total=_money(row["line_total"]),
                source_quotation_item_id=_as_uuid_opt(row.get("source_quotation_item_id")),
            )
            for row in rows
        ]

    def next_po_number(self, *, tenant_id: UUID) -> str:
        year = datetime.now(UTC).year
        try:
            with self._session() as session:
                self._exec(
                    session,
                    text(
                        """
                        INSERT INTO purchase_order_sequences (tenant_id, next_value)
                        VALUES (:tenant_id, 1)
                        ON CONFLICT (tenant_id) DO NOTHING
                        """
                    ),
                    {"tenant_id": tenant_id},
                )
                value = self._exec(
                    session,
                    text(
                        """
                        UPDATE purchase_order_sequences
                        SET next_value = next_value + 1
                        WHERE tenant_id = :tenant_id
                        RETURNING next_value - 1
                        """
                    ),
                    {"tenant_id": tenant_id},
                ).scalar()
                session.commit()
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        return f"PO-{year}-{int(value):04d}"

    def create_invoice(self, record: InvoiceRecord) -> InvoiceRecord:
        import json

        try:
            with self._session() as session:
                self._exec(
                    session,
                    text(
                        """
                        INSERT INTO invoices (
                            id, tenant_id, invoice_number, vendor_id, purchase_order_id, process_id,
                            currency, subtotal, tax, total, status, evidence_id, match_result_json
                        ) VALUES (
                            :id, :tenant_id, :invoice_number, :vendor_id, :purchase_order_id, :process_id,
                            :currency, :subtotal, :tax, :total, :status, :evidence_id, CAST(:match_result_json AS jsonb)
                        )
                        """
                    ),
                    {
                        "id": record.invoice_id,
                        "tenant_id": record.tenant_id,
                        "invoice_number": record.invoice_number,
                        "vendor_id": record.vendor_id,
                        "purchase_order_id": record.purchase_order_id,
                        "process_id": record.process_id,
                        "currency": record.currency,
                        "subtotal": record.subtotal,
                        "tax": record.tax,
                        "total": record.total,
                        "status": record.status,
                        "evidence_id": record.evidence_id,
                        "match_result_json": json.dumps(record.match_result),
                    },
                )
                for item in record.items:
                    self._exec(
                        session,
                        text(
                            """
                            INSERT INTO invoice_items (
                                id, tenant_id, invoice_id, description, quantity, unit_price,
                                line_total, purchase_order_item_id
                            ) VALUES (
                                :id, :tenant_id, :invoice_id, :description, :quantity, :unit_price,
                                :line_total, :purchase_order_item_id
                            )
                            """
                        ),
                        {
                            "id": item.item_id,
                            "tenant_id": record.tenant_id,
                            "invoice_id": record.invoice_id,
                            "description": item.description,
                            "quantity": item.quantity,
                            "unit_price": item.unit_price,
                            "line_total": item.line_total,
                            "purchase_order_item_id": item.purchase_order_item_id,
                        },
                    )
                session.commit()
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        found = self.get_invoice(tenant_id=record.tenant_id, invoice_id=record.invoice_id)
        if found is None:
            raise ProcurementUnavailableError("Invoice insert did not persist")
        return found

    def find_invoice_by_id(self, invoice_id: UUID) -> InvoiceRecord | None:
        try:
            with self._session() as session:
                row = self._exec(
                    session,
                    text("SELECT * FROM invoices WHERE id = :id"),
                    {"id": invoice_id},
                ).mappings().first()
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        if row is None:
            return None
        return _invoice_from_row(dict(row), [])

    def get_invoice(self, *, tenant_id: UUID, invoice_id: UUID) -> InvoiceRecord | None:
        try:
            with self._session() as session:
                row = self._exec(
                    session,
                    text("SELECT * FROM invoices WHERE tenant_id = :tenant_id AND id = :id"),
                    {"tenant_id": tenant_id, "id": invoice_id},
                ).mappings().first()
                if row is None:
                    return None
                items = self._invoice_items(session, tenant_id=tenant_id, invoice_id=invoice_id)
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        return _invoice_from_row(dict(row), items)

    def list_invoices_for_process(self, *, tenant_id: UUID, process_id: UUID) -> list[InvoiceRecord]:
        try:
            with self._session() as session:
                rows = self._exec(
                    session,
                    text(
                        """
                        SELECT * FROM invoices
                        WHERE tenant_id = :tenant_id AND process_id = :process_id
                        """
                    ),
                    {"tenant_id": tenant_id, "process_id": process_id},
                ).mappings().all()
                result = []
                for row in rows:
                    mapping = dict(row)
                    items = self._invoice_items(
                        session, tenant_id=tenant_id, invoice_id=_as_uuid(mapping["id"])
                    )
                    result.append(_invoice_from_row(mapping, items))
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        return result

    def update_invoice(self, record: InvoiceRecord) -> InvoiceRecord:
        import json

        try:
            with self._session() as session:
                self._exec(
                    session,
                    text(
                        """
                        UPDATE invoices
                        SET status = :status, match_result_json = CAST(:match_result_json AS jsonb),
                            updated_at = TIMEZONE('utc', NOW())
                        WHERE tenant_id = :tenant_id AND id = :id
                        """
                    ),
                    {
                        "status": record.status,
                        "match_result_json": json.dumps(record.match_result),
                        "tenant_id": record.tenant_id,
                        "id": record.invoice_id,
                    },
                )
                session.commit()
        except SQLAlchemyError as exc:
            raise _unavailable(exc)
        found = self.get_invoice(tenant_id=record.tenant_id, invoice_id=record.invoice_id)
        if found is None:
            raise ProcurementUnavailableError("Invoice update did not persist")
        return found

    def _invoice_items(self, session: Session, *, tenant_id: UUID, invoice_id: UUID) -> list[InvoiceItemRecord]:
        rows = self._exec(
            session,
            text(
                """
                SELECT * FROM invoice_items
                WHERE tenant_id = :tenant_id AND invoice_id = :invoice_id
                """
            ),
            {"tenant_id": tenant_id, "invoice_id": invoice_id},
        ).mappings().all()
        return [
            InvoiceItemRecord(
                item_id=_as_uuid(row["id"]),
                tenant_id=_as_uuid(row["tenant_id"]),
                invoice_id=_as_uuid(row["invoice_id"]),
                description=row["description"],
                quantity=Decimal(str(row["quantity"])),
                unit_price=_money(row["unit_price"]),
                line_total=_money(row["line_total"]),
                purchase_order_item_id=_as_uuid_opt(row.get("purchase_order_item_id")),
            )
            for row in rows
        ]


def _invoice_from_row(row: dict[str, Any], items: list[InvoiceItemRecord] | None = None) -> InvoiceRecord:
    match = row.get("match_result_json") or row.get("match_result") or {}
    if isinstance(match, str):
        import json

        match = json.loads(match)
    return InvoiceRecord(
        invoice_id=_as_uuid(row["id"]),
        tenant_id=_as_uuid(row["tenant_id"]),
        invoice_number=row["invoice_number"],
        vendor_id=_as_uuid(row["vendor_id"]),
        purchase_order_id=_as_uuid(row["purchase_order_id"]),
        process_id=_as_uuid(row["process_id"]),
        currency=row["currency"],
        subtotal=_money(row.get("subtotal")),
        tax=_money(row.get("tax")),
        total=_money(row.get("total")),
        status=row.get("status") or "RECEIVED",
        evidence_id=row.get("evidence_id"),
        match_result=match if isinstance(match, dict) else {},
        items=items or [],
    )


class RestProcurementRepository:
    def clear(self) -> None:
        return None

    def create_vendor(self, payload: CreateVendorInput) -> VendorRecord:
        vendor_id = payload.vendor_id or uuid4()
        row = rest_insert(
            "vendors",
            {
                "id": str(vendor_id),
                "tenant_id": str(payload.tenant_id),
                "vendor_code": payload.vendor_code,
                "legal_name": payload.legal_name,
                "status": payload.status,
                "phone": payload.phone,
                "website": payload.website,
                "notes": payload.notes,
            },
        )
        return _vendor_from_row(row)

    def create_vendor_contact(self, payload: CreateVendorContactInput) -> VendorContactRecord:
        if self.get_vendor(tenant_id=payload.tenant_id, vendor_id=payload.vendor_id) is None:
            raise VendorNotFoundError("Vendor not found in tenant")
        row = rest_insert(
            "vendor_contacts",
            {
                "id": str(payload.contact_id or uuid4()),
                "tenant_id": str(payload.tenant_id),
                "vendor_id": str(payload.vendor_id),
                "full_name": payload.full_name,
                "email": payload.email,
                "phone": payload.phone,
                "title": payload.title,
                "is_active": payload.is_active,
            },
        )
        return _contact_from_row(row)

    def get_vendor(self, *, tenant_id: UUID, vendor_id: UUID) -> VendorRecord | None:
        rows = rest_select("vendors", {"tenant_id": f"eq.{tenant_id}", "id": f"eq.{vendor_id}"})
        return None if not rows else _vendor_from_row(rows[0])

    def get_vendor_by_code(self, *, tenant_id: UUID, vendor_code: str) -> VendorRecord | None:
        rows = rest_select("vendors", {"tenant_id": f"eq.{tenant_id}", "vendor_code": f"eq.{vendor_code}"})
        return None if not rows else _vendor_from_row(rows[0])

    def list_vendors(self, *, tenant_id: UUID) -> list[VendorRecord]:
        return [_vendor_from_row(row) for row in rest_select("vendors", {"tenant_id": f"eq.{tenant_id}"})]

    def list_vendor_contacts(self, *, tenant_id: UUID, vendor_id: UUID) -> list[VendorContactRecord]:
        rows = rest_select(
            "vendor_contacts",
            {"tenant_id": f"eq.{tenant_id}", "vendor_id": f"eq.{vendor_id}"},
        )
        return [_contact_from_row(row) for row in rows]

    def create_quotation(self, payload: CreateQuotationInput) -> QuotationRecord:
        quotation_id = payload.quotation_id or uuid4()
        row = rest_insert(
            "quotations",
            {
                "id": str(quotation_id),
                "tenant_id": str(payload.tenant_id),
                "quotation_number": payload.quotation_number or f"QT-{quotation_id.hex[:8].upper()}",
                "vendor_id": str(payload.vendor_id),
                "process_id": str(payload.process_id),
                "currency": payload.currency,
                "subtotal": str(payload.subtotal or 0),
                "tax": str(payload.tax),
                "total": str(payload.total or payload.subtotal or 0),
                "status": payload.status,
                "evidence_id": payload.evidence_id,
            },
        )
        items: list[QuotationItemRecord] = []
        for line in payload.items:
            qty = Decimal(str(line.quantity))
            price = _money(line.unit_price)
            inserted = rest_insert(
                "quotation_items",
                {
                    "tenant_id": str(payload.tenant_id),
                    "quotation_id": str(quotation_id),
                    "description": line.description,
                    "quantity": str(qty),
                    "unit_price": str(price),
                    "line_total": str(_money(qty * price)),
                },
            )
            items.append(
                QuotationItemRecord(
                    item_id=_as_uuid(inserted["id"]),
                    tenant_id=payload.tenant_id,
                    quotation_id=quotation_id,
                    description=line.description,
                    quantity=qty,
                    unit_price=price,
                    line_total=_money(qty * price),
                )
            )
        return _quote_from_row(row, items)

    def get_quotation(self, *, tenant_id: UUID, quotation_id: UUID) -> QuotationRecord | None:
        rows = rest_select("quotations", {"tenant_id": f"eq.{tenant_id}", "id": f"eq.{quotation_id}"})
        if not rows:
            return None
        items = rest_select(
            "quotation_items",
            {"tenant_id": f"eq.{tenant_id}", "quotation_id": f"eq.{quotation_id}"},
        )
        mapped = [
            QuotationItemRecord(
                item_id=_as_uuid(item["id"]),
                tenant_id=_as_uuid(item["tenant_id"]),
                quotation_id=_as_uuid(item["quotation_id"]),
                description=item["description"],
                quantity=Decimal(str(item["quantity"])),
                unit_price=_money(item["unit_price"]),
                line_total=_money(item["line_total"]),
            )
            for item in items
        ]
        return _quote_from_row(rows[0], mapped)

    def list_quotations_for_process(self, *, tenant_id: UUID, process_id: UUID) -> list[QuotationRecord]:
        rows = rest_select("quotations", {"tenant_id": f"eq.{tenant_id}", "process_id": f"eq.{process_id}"})
        result: list[QuotationRecord] = []
        for row in rows:
            found = self.get_quotation(tenant_id=tenant_id, quotation_id=_as_uuid(row["id"]))
            if found is not None:
                result.append(found)
        return result

    def count_quotations_for_process(self, *, tenant_id: UUID, process_id: UUID) -> int:
        return len(self.list_quotations_for_process(tenant_id=tenant_id, process_id=process_id))

    def create_purchase_order(self, record: PurchaseOrderRecord) -> PurchaseOrderRecord:
        rest_insert(
            "purchase_orders",
            {
                "id": str(record.purchase_order_id),
                "tenant_id": str(record.tenant_id),
                "po_number": record.po_number,
                "process_id": str(record.process_id),
                "vendor_id": str(record.vendor_id),
                "workflow_plan_id": None if record.workflow_plan_id is None else str(record.workflow_plan_id),
                "workflow_step_id": None if record.workflow_step_id is None else str(record.workflow_step_id),
                "currency": record.currency,
                "subtotal": str(record.subtotal),
                "tax": str(record.tax),
                "total": str(record.total),
                "status": record.status,
                "created_by": record.created_by,
                "selected_quotation_id": None
                if record.selected_quotation_id is None
                else str(record.selected_quotation_id),
                "notes": record.notes,
            },
        )
        stored_items: list[PurchaseOrderItemRecord] = []
        try:
            for item in record.items:
                inserted = rest_insert(
                    "purchase_order_items",
                    {
                        "id": str(item.item_id),
                        "tenant_id": str(record.tenant_id),
                        "purchase_order_id": str(record.purchase_order_id),
                        "description": item.description,
                        "quantity": str(item.quantity),
                        "unit_price": str(item.unit_price),
                        "line_total": str(item.line_total),
                    },
                )
                stored_items.append(
                    item.model_copy(update={"item_id": _as_uuid(inserted.get("id", item.item_id))})
                )
        except Exception as exc:
            logger.exception("purchase_order_item_insert_failed")
            raise ProcurementUnavailableError("Purchase order item insert failed") from exc
        return record.model_copy(update={"items": stored_items})

    def get_purchase_order(self, *, tenant_id: UUID, purchase_order_id: UUID) -> PurchaseOrderRecord | None:
        rows = rest_select(
            "purchase_orders", {"tenant_id": f"eq.{tenant_id}", "id": f"eq.{purchase_order_id}"}
        )
        if not rows:
            return None
        items = rest_select(
            "purchase_order_items",
            {"tenant_id": f"eq.{tenant_id}", "purchase_order_id": f"eq.{purchase_order_id}"},
        )
        mapped = [
            PurchaseOrderItemRecord(
                item_id=_as_uuid(item["id"]),
                tenant_id=_as_uuid(item["tenant_id"]),
                purchase_order_id=_as_uuid(item["purchase_order_id"]),
                description=item["description"],
                quantity=Decimal(str(item["quantity"])),
                unit_price=_money(item["unit_price"]),
                line_total=_money(item["line_total"]),
                source_quotation_item_id=_as_uuid_opt(item.get("source_quotation_item_id")),
            )
            for item in items
        ]
        return _po_from_row(rows[0], mapped)

    def get_purchase_order_by_step(
        self, *, tenant_id: UUID, workflow_step_id: UUID
    ) -> PurchaseOrderRecord | None:
        rows = rest_select(
            "purchase_orders",
            {"tenant_id": f"eq.{tenant_id}", "workflow_step_id": f"eq.{workflow_step_id}"},
        )
        if not rows:
            return None
        return self.get_purchase_order(tenant_id=tenant_id, purchase_order_id=_as_uuid(rows[0]["id"]))

    def list_purchase_orders_for_process(
        self, *, tenant_id: UUID, process_id: UUID
    ) -> list[PurchaseOrderRecord]:
        rows = rest_select(
            "purchase_orders", {"tenant_id": f"eq.{tenant_id}", "process_id": f"eq.{process_id}"}
        )
        result = []
        for row in rows:
            found = self.get_purchase_order(tenant_id=tenant_id, purchase_order_id=_as_uuid(row["id"]))
            if found is not None:
                result.append(found)
        return result

    def next_po_number(self, *, tenant_id: UUID) -> str:
        year = datetime.now(UTC).year
        return f"PO-{year}-{uuid4().hex[:8].upper()}"

    def create_invoice(self, record: InvoiceRecord) -> InvoiceRecord:
        rest_insert(
            "invoices",
            {
                "id": str(record.invoice_id),
                "tenant_id": str(record.tenant_id),
                "invoice_number": record.invoice_number,
                "vendor_id": str(record.vendor_id),
                "purchase_order_id": str(record.purchase_order_id),
                "process_id": str(record.process_id),
                "currency": record.currency,
                "subtotal": str(record.subtotal),
                "tax": str(record.tax),
                "total": str(record.total),
                "status": record.status,
                "evidence_id": record.evidence_id,
                "match_result_json": record.match_result,
            },
        )
        for item in record.items:
            rest_insert(
                "invoice_items",
                {
                    "id": str(item.item_id),
                    "tenant_id": str(record.tenant_id),
                    "invoice_id": str(record.invoice_id),
                    "description": item.description,
                    "quantity": str(item.quantity),
                    "unit_price": str(item.unit_price),
                    "line_total": str(item.line_total),
                    "purchase_order_item_id": (
                        None if item.purchase_order_item_id is None else str(item.purchase_order_item_id)
                    ),
                },
            )
        return record

    def find_invoice_by_id(self, invoice_id: UUID) -> InvoiceRecord | None:
        rows = rest_select("invoices", {"id": f"eq.{invoice_id}"})
        if not rows:
            return None
        return _invoice_from_row(dict(rows[0]), [])

    def get_invoice(self, *, tenant_id: UUID, invoice_id: UUID) -> InvoiceRecord | None:
        rows = rest_select("invoices", {"tenant_id": f"eq.{tenant_id}", "id": f"eq.{invoice_id}"})
        if not rows:
            return None
        items = rest_select(
            "invoice_items",
            {"tenant_id": f"eq.{tenant_id}", "invoice_id": f"eq.{invoice_id}"},
        )
        mapped = [
            InvoiceItemRecord(
                item_id=_as_uuid(item["id"]),
                tenant_id=_as_uuid(item["tenant_id"]),
                invoice_id=_as_uuid(item["invoice_id"]),
                description=item["description"],
                quantity=Decimal(str(item["quantity"])),
                unit_price=_money(item["unit_price"]),
                line_total=_money(item["line_total"]),
                purchase_order_item_id=_as_uuid_opt(item.get("purchase_order_item_id")),
            )
            for item in items
        ]
        return _invoice_from_row(rows[0], mapped)

    def list_invoices_for_process(self, *, tenant_id: UUID, process_id: UUID) -> list[InvoiceRecord]:
        rows = rest_select("invoices", {"tenant_id": f"eq.{tenant_id}", "process_id": f"eq.{process_id}"})
        result = []
        for row in rows:
            found = self.get_invoice(tenant_id=tenant_id, invoice_id=_as_uuid(row["id"]))
            if found is not None:
                result.append(found)
        return result

    def update_invoice(self, record: InvoiceRecord) -> InvoiceRecord:
        from app.core.supabase_rest import rest_update

        rest_update(
            "invoices",
            {"id": f"eq.{record.invoice_id}", "tenant_id": f"eq.{record.tenant_id}"},
            {"status": record.status, "match_result_json": record.match_result},
        )
        return record
