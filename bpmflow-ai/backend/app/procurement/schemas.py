"""Tenant-scoped procurement records. Monetary values are Decimal."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

VendorStatus = Literal["active", "inactive"]
QuotationStatus = Literal["REQUESTED", "RECEIVED", "SELECTED", "REJECTED", "CANCELLED"]
PurchaseOrderStatus = Literal["DRAFT", "ISSUED", "CANCELLED"]


class VendorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_id: UUID
    tenant_id: UUID
    vendor_code: str
    legal_name: str
    status: VendorStatus = "active"
    phone: str | None = None
    website: str | None = None
    notes: str | None = None


class VendorContactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: UUID
    tenant_id: UUID
    vendor_id: UUID
    full_name: str
    email: str | None = None
    phone: str | None = None
    title: str | None = None
    is_active: bool = True


class QuotationItemRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    quotation_id: UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class QuotationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quotation_id: UUID
    tenant_id: UUID
    quotation_number: str
    vendor_id: UUID
    process_id: UUID
    currency: str
    subtotal: Decimal
    tax: Decimal = Decimal("0")
    total: Decimal
    status: QuotationStatus = "RECEIVED"
    quotation_date: date | None = None
    evidence_id: str | None = None
    document_id: UUID | None = None
    workflow_step_id: UUID | None = None
    items: list[QuotationItemRecord] = Field(default_factory=list)


class PurchaseOrderItemRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    purchase_order_id: UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    source_quotation_item_id: UUID | None = None


class PurchaseOrderRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_order_id: UUID
    tenant_id: UUID
    po_number: str
    process_id: UUID
    vendor_id: UUID
    currency: str
    subtotal: Decimal
    tax: Decimal = Decimal("0")
    total: Decimal
    status: PurchaseOrderStatus = "DRAFT"
    workflow_plan_id: UUID | None = None
    workflow_step_id: UUID | None = None
    created_by: str | None = None
    selected_quotation_id: UUID | None = None
    notes: str | None = None
    items: list[PurchaseOrderItemRecord] = Field(default_factory=list)
    created_at: datetime | None = None


class CreateVendorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    vendor_code: str
    legal_name: str
    vendor_id: UUID | None = None
    status: VendorStatus = "active"
    phone: str | None = None
    website: str | None = None
    notes: str | None = None

    @field_validator("vendor_code")
    @classmethod
    def _code_required(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("vendor_code is required")
        return text


class CreateVendorContactInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    vendor_id: UUID
    full_name: str
    contact_id: UUID | None = None
    email: str | None = None
    phone: str | None = None
    title: str | None = None
    is_active: bool = True


class LineItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    quantity: Decimal = Field(ge=0)
    unit_price: Decimal = Field(ge=0)
    purchase_order_item_id: UUID | None = None


class CreateQuotationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    vendor_id: UUID
    process_id: UUID
    currency: str
    quotation_number: str | None = None
    quotation_id: UUID | None = None
    subtotal: Decimal | None = None
    tax: Decimal = Decimal("0")
    total: Decimal | None = None
    status: QuotationStatus = "RECEIVED"
    evidence_id: str | None = None
    items: list[LineItemInput] = Field(default_factory=list)


class CreatePurchaseOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    process_id: UUID
    vendor_ref: str
    currency: str
    amount: Decimal = Field(ge=0)
    tax: Decimal = Field(default=Decimal("0"), ge=0)
    workflow_plan_id: UUID | None = None
    workflow_step_id: UUID | None = None
    budget_available: Decimal | None = None
    min_quotations: int = 0
    notes: str | None = None
    created_by: str | None = None
    items: list[LineItemInput] = Field(default_factory=list)
    quotation_facts: list[dict] = Field(default_factory=list)


InvoiceStatus = Literal[
    "RECEIVED",
    "MATCHING",
    "MATCHED",
    "MISMATCH",
    "EXCEPTION",
    "CANCELLED",
]


class InvoiceItemRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    invoice_id: UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    purchase_order_item_id: UUID | None = None


class InvoiceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: UUID
    tenant_id: UUID
    invoice_number: str
    vendor_id: UUID
    purchase_order_id: UUID
    process_id: UUID
    currency: str
    subtotal: Decimal
    tax: Decimal = Decimal("0")
    total: Decimal
    status: InvoiceStatus = "RECEIVED"
    invoice_date: date | None = None
    received_at: datetime | None = None
    evidence_id: str | None = None
    document_id: UUID | None = None
    match_result: dict = Field(default_factory=dict)
    workflow_step_id: UUID | None = None
    items: list[InvoiceItemRecord] = Field(default_factory=list)


class CreateInvoiceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    process_id: UUID
    purchase_order_id: UUID | None = None
    vendor_ref: str | None = None
    invoice_number: str
    currency: str
    total: Decimal | None = Field(default=None, ge=0)
    subtotal: Decimal | None = Field(default=None, ge=0)
    tax: Decimal = Field(default=Decimal("0"), ge=0)
    invoice_id: UUID | None = None
    evidence_id: str | None = None
    items: list[LineItemInput] = Field(default_factory=list)


class InvoiceMatchResultRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: UUID
    purchase_order_id: UUID
    process_id: UUID
    tenant_id: UUID
    status: str
    matched: bool
    discrepancy_codes: list[str] = Field(default_factory=list)
    discrepancy_details: list[str] = Field(default_factory=list)
    matched_amount: Decimal | None = None
    invoice_amount: Decimal | None = None
    po_amount: Decimal | None = None
    currency: str | None = None
    vendor_match: bool = False
    line_match: bool = False
    evidence_refs: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    amount_tolerance: str = "0.00"
