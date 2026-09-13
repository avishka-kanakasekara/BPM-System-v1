"""Typed canonical ProcessContext. Facts stay NULL when unknown."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

FactSource = Literal[
    "authenticated",
    "extracted_evidence",
    "company_repository",
    "policy_repository",
    "agent_derived",
    "unspecified",
]


class SourcedDecimal(BaseModel):
    """A decimal business value with provenance. LLM must never set this."""

    model_config = ConfigDict(extra="forbid")

    value: Decimal | None = None
    currency: str | None = None
    source: FactSource = "unspecified"


class RequesterIdentity(BaseModel):
    """Authentication user vs company employee/resource — never assumed equal."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID | None = None
    employee_resource_id: UUID | None = None
    name: str | None = None
    email: str | None = None
    department: str | None = None
    identity_mapped: bool = False


class ApproverIdentity(BaseModel):
    """Designated approver. NULL until explicitly assigned — never invented."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID | None = None
    employee_resource_id: UUID | None = None
    role: str | None = None
    email: str | None = None
    approval_id: UUID | None = None


class PurchaseItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    quantity: Decimal | None = None
    unit_amount: Decimal | None = None
    currency: str | None = None


class PurchaseFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    vendor_id: str | None = None
    vendor_name: str | None = None
    cost_centre: str | None = None
    purchase_request_id: str | None = None
    items: list[PurchaseItem] = Field(default_factory=list)
    amount_source: FactSource = "unspecified"


class BudgetFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_id: UUID | None = None
    allocated_amount: Decimal | None = None
    used_amount: Decimal | None = None
    available_amount: Decimal | None = None
    currency: str | None = None
    source: FactSource = "unspecified"


class QuotationFact(BaseModel):
    """One quotation. Count is len(quotations), never a collapsed token."""

    model_config = ConfigDict(extra="forbid")

    quotation_id: str
    vendor: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    document_id: UUID | None = None
    evidence_id: str | None = None
    status: str | None = None
    source: FactSource = "extracted_evidence"


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    document_id: UUID | None = None
    source: str | None = None
    type: str | None = None
    page: int | None = None
    section: str | None = None
    field: str | None = None


class PolicyRefs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_ids: list[UUID] = Field(default_factory=list)
    policy_version: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class RiskSnapshot(BaseModel):
    """Copy of Agent 4 risk output for later agents — not an approval."""

    model_config = ConfigDict(extra="forbid")

    categories: list[str] = Field(default_factory=list)
    risk_level: str | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class DiscoveryActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    actor: str | None = None
    system: str | None = None


class DiscoveryDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predecessor: str
    successor: str


class DiscoverySummary(BaseModel):
    """Agent 1 informational slice. Agent 1 still does not approve or set stage."""

    model_config = ConfigDict(extra="forbid")

    discovery_status: str | None = None
    message_id: UUID | None = None
    trace_id: UUID | None = None
    activities: list[DiscoveryActivity] = Field(default_factory=list)
    dependencies: list[DiscoveryDependency] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ProcessContext(BaseModel):
    """Single tenant-scoped business context for Agents 1–4."""

    model_config = ConfigDict(extra="forbid")

    process_id: UUID
    tenant_id: UUID | None = None
    request_id: UUID = Field(default_factory=uuid4)
    schema_version: str = "1.0.0"
    requester: RequesterIdentity = Field(default_factory=RequesterIdentity)
    purchase: PurchaseFacts = Field(default_factory=PurchaseFacts)
    budget: BudgetFacts = Field(default_factory=BudgetFacts)
    quotations: list[QuotationFact] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    approver: ApproverIdentity = Field(default_factory=ApproverIdentity)
    policy: PolicyRefs = Field(default_factory=PolicyRefs)
    risk: RiskSnapshot = Field(default_factory=RiskSnapshot)
    discovery: DiscoverySummary = Field(default_factory=DiscoverySummary)
    updated_at: datetime | None = None

    @field_validator("purchase", mode="before")
    @classmethod
    def _coerce_purchase(cls, value: object) -> object:
        return value or PurchaseFacts()

    @property
    def quotation_count(self) -> int:
        return len(self.quotations)

    def missing_fields(self, fields: list[str]) -> list[str]:
        missing: list[str] = []
        for field in fields:
            if self._resolve_path(field) in (None, "", []):
                missing.append(field)
        return missing

    def _resolve_path(self, path: str) -> object:
        current: object = self
        for part in path.split("."):
            if current is None:
                return None
            current = getattr(current, part, None) if not isinstance(current, dict) else current.get(part)
        return current
