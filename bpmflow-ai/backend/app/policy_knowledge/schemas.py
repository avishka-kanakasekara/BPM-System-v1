"""Pydantic schemas for the Company Policy & Knowledge Repository."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .constants import (
    PolicyCategory,
    PolicyOperator,
    PolicyRetrievalStatus,
    PolicyRuleType,
    PolicyVersionStatus,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class PolicyRule(BaseModel):
    """Structured deterministic rule used by Agent 4 risk analysis."""

    id: UUID = Field(default_factory=uuid4)
    rule_type: PolicyRuleType
    operator: PolicyOperator | None = PolicyOperator.GT
    threshold_value: Decimal | None = None
    currency: str | None = None
    required_approval: str | None = None
    required_roles: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    sla_hours: Decimal | None = None
    description: str | None = None
    source_chunk_id: UUID | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PolicyChunk(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    chunk_index: int
    page_number: int | None = None
    section_title: str | None = None
    text_content: str
    embedding: list[float] | None = None


class PolicyVersionRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    policy_id: UUID
    tenant_id: UUID
    version_label: str
    status: PolicyVersionStatus = PolicyVersionStatus.DRAFT
    document_name: str
    document_type: str
    source_document_id: UUID | None = None
    storage_path: str | None = None
    effective_from: datetime = Field(default_factory=utc_now)
    effective_to: datetime | None = None
    uploaded_by: UUID | None = None
    uploaded_at: datetime = Field(default_factory=utc_now)
    access_scope: str = "tenant"
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    chunks: list[PolicyChunk] = Field(default_factory=list)
    rules: list[PolicyRule] = Field(default_factory=list)


class CompanyPolicyRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    name: str
    category: PolicyCategory
    description: str | None = None
    created_by: UUID | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    versions: list[PolicyVersionRecord] = Field(default_factory=list)


class PolicyCreateRequest(BaseModel):
    """Metadata for creating/uploading a policy version."""

    name: str = Field(min_length=1, max_length=200)
    category: PolicyCategory
    version_label: str = Field(min_length=1, max_length=64)
    description: str | None = None
    document_type: str = Field(default="txt", min_length=1, max_length=32)
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    activate: bool = True
    access_scope: str = "tenant"
    # Optional explicit structured rules (preferred over text extraction alone).
    rules: list[PolicyRule] = Field(default_factory=list)
    # Optional plain-text body when not uploading a binary file.
    text_content: str | None = None


class PolicyEvidenceItem(BaseModel):
    document_id: UUID
    policy_id: UUID
    policy_name: str
    version: str
    category: PolicyCategory
    page: int | None = None
    section: str | None = None
    text: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    chunk_id: UUID | None = None


class PolicyRetrievalResult(BaseModel):
    query: str
    status: PolicyRetrievalStatus
    policy_id: UUID | None = None
    policy_name: str | None = None
    version: str | None = None
    category: PolicyCategory | None = None
    evidence: list[PolicyEvidenceItem] = Field(default_factory=list)
    rules: list[PolicyRule] = Field(default_factory=list)
    confidence: Decimal | None = None
    conflicting_policy_ids: list[UUID] = Field(default_factory=list)
    message: str | None = None


class PolicyRiskSnapshot(BaseModel):
    """Normalized policy facts supplied to the deterministic risk engine."""

    status: PolicyRetrievalStatus
    query: str
    high_value_threshold: Decimal | None = None
    approval_threshold: Decimal | None = None
    currency: str | None = None
    required_evidence: list[str] = Field(default_factory=list)
    required_roles: list[str] = Field(default_factory=list)
    enforce_segregation_of_duties: bool = True
    sla_hours: Decimal | None = None
    available_budget: Decimal | None = None
    evidence: list[PolicyEvidenceItem] = Field(default_factory=list)
    rules: list[PolicyRule] = Field(default_factory=list)
    policy_versions: list[str] = Field(default_factory=list)
    confidence: Decimal | None = None
    message: str | None = None
    invoice_amount_tolerance: Decimal | None = None


class PolicyDecisionPackage(BaseModel):
    """Auditable Agent 4 risk/policy decision summary."""

    process_id: UUID
    risk_level: str | None = None
    risk_findings: list[dict[str, Any]] = Field(default_factory=list)
    policy_evidence: list[PolicyEvidenceItem] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    controls_required: list[str] = Field(default_factory=list)
    approval_required: bool = False
    blocking: bool = False
    confidence: Decimal | None = None
    policy_version: str | None = None
    generated_at: datetime = Field(default_factory=utc_now)
    policy_retrieval_status: PolicyRetrievalStatus | None = None
