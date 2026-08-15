"""Pydantic schemas for Agent 3 Resource Allocation (local contract)."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from uuid import UUID, uuid4

from .constants import (
    ResourceType,
    ExclusionReason,
    RecommendationStatus,
    GapAlternativeType,
    GapType,
    MessageType,
    SCHEMA_VERSION,
    AGENT_3_SENDER,
    AGENT_4_RECEIVER,
)


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def validate_timezone_aware(value: datetime, field_name: str) -> datetime:
    """Ensure a datetime is timezone-aware (UTC-compatible)."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware (UTC)")
    return value


_AWARE_DATETIME_FIELDS = (
    "timestamp",
    "task_deadline",
    "available_from",
    "available_until",
    "evidence_checked_at",
    "evidence_valid_until",
    "valid_from",
    "valid_until",
)


# ============================================================================
# Message Metadata
# ============================================================================

class AgentMessageMetadata(BaseModel):
    """Metadata for inter-agent messages."""

    model_config = ConfigDict(extra="forbid")

    message_id: UUID = Field(default_factory=uuid4)
    schema_version: str = SCHEMA_VERSION
    correlation_id: UUID
    process_instance_id: UUID
    task_id: UUID
    tenant_id: UUID
    sender: str = AGENT_3_SENDER
    receiver: str = AGENT_4_RECEIVER
    message_type: MessageType
    timestamp: datetime = Field(default_factory=utc_now)

    @field_validator("timestamp", mode="after")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        return validate_timezone_aware(value, "timestamp")


# ============================================================================
# Resource Requirements (from Agent 4)
# ============================================================================

class HumanResourceRequirement(BaseModel):
    """Requirements for HUMAN resource allocation."""

    model_config = ConfigDict(extra="forbid")

    resource_type: Literal[ResourceType.HUMAN] = ResourceType.HUMAN
    required_roles: List[str] = Field(default_factory=list)
    mandatory_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    required_authority: Optional[str] = None
    requester_id: UUID
    task_deadline: datetime
    estimated_effort_hours: Decimal = Field(ge=Decimal("0"))
    process_stage: str

    @field_validator("task_deadline", mode="after")
    @classmethod
    def validate_task_deadline(cls, value: datetime) -> datetime:
        return validate_timezone_aware(value, "task_deadline")


class BudgetResourceRequirement(BaseModel):
    """Requirements for BUDGET resource validation."""

    model_config = ConfigDict(extra="forbid")

    resource_type: Literal[ResourceType.BUDGET] = ResourceType.BUDGET
    required_amount: Decimal = Field(ge=Decimal("0"))
    currency: str
    cost_centre: Optional[str] = None
    requester_id: UUID
    task_deadline: datetime
    process_stage: str

    @field_validator("task_deadline", mode="after")
    @classmethod
    def validate_task_deadline(cls, value: datetime) -> datetime:
        return validate_timezone_aware(value, "task_deadline")


class AllocationRequest(BaseModel):
    """Main allocation request from Agent 4."""

    model_config = ConfigDict(extra="forbid")

    metadata: AgentMessageMetadata
    human_requirements: Optional[HumanResourceRequirement] = None
    budget_requirements: Optional[BudgetResourceRequirement] = None


# ============================================================================
# Resource Evidence
# ============================================================================

class HumanResourceEvidence(BaseModel):
    """Evidence data for a HUMAN resource."""
    resource_id: UUID
    tenant_id: UUID
    resource_type: Literal[ResourceType.HUMAN] = ResourceType.HUMAN
    name: str
    is_active: bool = True
    roles: List[str] = Field(default_factory=list)
    mandatory_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    authority: Optional[str] = None
    available_from: datetime
    available_until: Optional[datetime] = None
    current_workload_percentage: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    max_workload_percentage: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    projected_workload_percentage: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    segregation_of_duties_conflicts: List[UUID] = Field(default_factory=list)
    conflict_of_interest_flags: List[str] = Field(default_factory=list)
    evidence_checked_at: datetime
    evidence_valid_until: datetime
    evidence_references: Dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "available_from",
        "available_until",
        "evidence_checked_at",
        "evidence_valid_until",
        mode="after",
    )
    @classmethod
    def validate_datetimes(cls, value: Optional[datetime], info) -> Optional[datetime]:
        if value is not None:
            return validate_timezone_aware(value, info.field_name)
        return value


class BudgetResourceEvidence(BaseModel):
    """Evidence data for a BUDGET resource."""
    resource_id: UUID
    tenant_id: UUID
    resource_type: Literal[ResourceType.BUDGET] = ResourceType.BUDGET
    name: str
    available_balance: Decimal = Field(ge=Decimal("0"))
    currency: str
    cost_centre: Optional[str] = None
    valid_from: datetime
    valid_until: Optional[datetime] = None
    authorization_limit: Optional[Decimal] = Field(ge=Decimal("0"), default=None)
    evidence_checked_at: datetime
    evidence_valid_until: datetime
    evidence_references: Dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "valid_from",
        "valid_until",
        "evidence_checked_at",
        "evidence_valid_until",
        mode="after",
    )
    @classmethod
    def validate_datetimes(cls, value: Optional[datetime], info) -> Optional[datetime]:
        if value is not None:
            return validate_timezone_aware(value, info.field_name)
        return value


# ============================================================================
# Eligibility and Exclusions
# ============================================================================

class ExclusionReasonEntry(BaseModel):
    """Single exclusion reason with details."""
    reason: ExclusionReason
    description: str
    evidence_reference: Optional[str] = None


class ExcludedResource(BaseModel):
    """Resource excluded with one or more reasons."""
    resource_id: UUID
    resource_type: ResourceType
    name: str
    exclusion_reasons: List[ExclusionReasonEntry] = Field(default_factory=list)


# ============================================================================
# Scoring and Ranking
# ============================================================================

class ScoreBreakdown(BaseModel):
    """Detailed score breakdown for a ranked candidate."""
    role_match: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    skill_match: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    availability_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    workload_fit: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    authority_match: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    total_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @field_validator("total_score")
    @classmethod
    def validate_total_score(cls, v: Decimal, info) -> Decimal:
        """Ensure total score matches weighted sum."""
        data = info.data
        from .constants import SCORING_WEIGHTS
        expected = (
            data.get("role_match", Decimal("0")) * Decimal(str(SCORING_WEIGHTS["role_match"])) +
            data.get("skill_match", Decimal("0")) * Decimal(str(SCORING_WEIGHTS["skill_match"])) +
            data.get("availability_score", Decimal("0")) * Decimal(str(SCORING_WEIGHTS["availability_score"])) +
            data.get("workload_fit", Decimal("0")) * Decimal(str(SCORING_WEIGHTS["workload_fit"])) +
            data.get("authority_match", Decimal("0")) * Decimal(str(SCORING_WEIGHTS["authority_match"]))
        )
        if abs(v - expected) > Decimal("0.01"):
            raise ValueError(f"Total score {v} does not match weighted sum {expected}")
        return v


class RankedHumanCandidate(BaseModel):
    """Eligible HUMAN resource with deterministic ranking metadata."""
    resource_id: UUID
    resource_type: Literal[ResourceType.HUMAN] = ResourceType.HUMAN
    name: str
    rank: int = Field(ge=1)
    allocation_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    score_breakdown: ScoreBreakdown
    current_workload_percentage: Decimal
    projected_workload_percentage: Decimal
    available_from: datetime
    available_until: Optional[datetime] = None
    evidence_refs: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("available_from", "available_until", mode="after")
    @classmethod
    def validate_datetimes(cls, value: Optional[datetime], info) -> Optional[datetime]:
        if value is not None:
            return validate_timezone_aware(value, info.field_name)
        return value

    @model_validator(mode="after")
    def validate_score_alignment(self) -> "RankedHumanCandidate":
        if self.allocation_score != self.score_breakdown.total_score:
            raise ValueError(
                "allocation_score must match score_breakdown.total_score"
            )
        return self


# Backward-compatible alias used internally before Phase 1.1 naming.
RankedCandidate = RankedHumanCandidate


# ============================================================================
# Budget Validation
# ============================================================================

class BudgetValidationResult(BaseModel):
    """Budget validation results."""
    resource_id: UUID
    name: str
    sufficient_balance: bool
    cost_centre_match: bool
    currency_match: bool
    validity_period_valid: bool
    within_authorization_limit: bool
    available_balance: Decimal
    required_amount: Decimal
    evidence_references: Dict[str, Any] = Field(default_factory=dict)


BudgetValidationChecks = BudgetValidationResult


# ============================================================================
# Requirement Results
# ============================================================================

class RequirementResult(BaseModel):
    """Result for a single resource requirement."""
    resource_type: ResourceType
    eligible_candidates: List[RankedHumanCandidate] = Field(default_factory=list)
    excluded_resources: List[ExcludedResource] = Field(default_factory=list)
    budget_validation: Optional[BudgetValidationResult] = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> "RequirementResult":
        if self.resource_type == ResourceType.HUMAN and self.budget_validation is not None:
            raise ValueError("HUMAN requirement results must not include budget_validation")
        if self.resource_type == ResourceType.BUDGET and self.eligible_candidates:
            raise ValueError("BUDGET requirement results must not include ranked HUMAN candidates")
        return self


# ============================================================================
# Resource Gaps and Alternatives
# ============================================================================

class ResourceGap(BaseModel):
    """Detected resource gap from a completed business analysis."""
    gap_type: GapType
    resource_type: ResourceType
    gap_description: str
    eligible_count: int = 0
    excluded_count: int = 0


class ResourceAlternative(BaseModel):
    """Alternative action for resource gap."""
    alternative_type: GapAlternativeType
    description: str
    requires_approval: bool = True
    estimated_effort_hours: Optional[Decimal] = None
    cost_impact: Optional[Decimal] = None


# ============================================================================
# Allocation Recommendation
# ============================================================================

_SUCCESSFUL_STATUSES = {
    RecommendationStatus.GENERATED,
    RecommendationStatus.PENDING_HUMAN_APPROVAL,
    RecommendationStatus.SUPERSEDED,
}


class AllocationRecommendation(BaseModel):
    """Final allocation recommendation from Agent 3."""
    metadata: AgentMessageMetadata
    status: RecommendationStatus = RecommendationStatus.PENDING_HUMAN_APPROVAL
    human_requirement_result: Optional[RequirementResult] = None
    budget_requirement_result: Optional[RequirementResult] = None
    resource_gaps: List[ResourceGap] = Field(default_factory=list)
    alternatives: List[ResourceAlternative] = Field(default_factory=list)
    explanation: str = ""
    requires_human_approval: bool = True
    manual_intervention_required: bool = False
    confidence: Optional[Decimal] = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    limitations: List[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: Optional[bool] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: RecommendationStatus) -> RecommendationStatus:
        """Agent 3 can only use specific statuses."""
        allowed = {
            RecommendationStatus.GENERATED,
            RecommendationStatus.PENDING_HUMAN_APPROVAL,
            RecommendationStatus.SUPERSEDED,
            RecommendationStatus.FAILED,
        }
        if v not in allowed:
            raise ValueError(f"Agent 3 cannot use status {v}")
        return v

    @model_validator(mode="after")
    def validate_status_contract(self) -> "AllocationRecommendation":
        if self.status in _SUCCESSFUL_STATUSES:
            if not self.explanation or not self.explanation.strip():
                raise ValueError(
                    "Successful recommendation requires a non-empty explanation"
                )
            if self.confidence is None:
                raise ValueError("Successful recommendation requires confidence")
            if not self.requires_human_approval:
                raise ValueError("Successful recommendation requires human approval")
            if self.manual_intervention_required:
                raise ValueError(
                    "Successful recommendation must not require manual intervention"
                )
            if self.error_code or self.error_message or self.retryable is not None:
                raise ValueError(
                    "Successful recommendation must not include technical error fields"
                )
        elif self.status == RecommendationStatus.FAILED:
            if not self.error_code or not self.error_code.strip():
                raise ValueError("FAILED recommendation requires error_code")
            if not self.error_message or not self.error_message.strip():
                raise ValueError("FAILED recommendation requires error_message")
            if self.retryable is None:
                raise ValueError("FAILED recommendation requires retryable")
            if self.requires_human_approval:
                raise ValueError(
                    "FAILED recommendation must not require human approval"
                )
            if not self.manual_intervention_required:
                raise ValueError(
                    "FAILED recommendation requires manual intervention"
                )
            if self.human_requirement_result is not None:
                raise ValueError(
                    "FAILED recommendation must not include human requirement results"
                )
            if self.budget_requirement_result is not None:
                raise ValueError(
                    "FAILED recommendation must not include budget requirement results"
                )
            if self.resource_gaps or self.alternatives:
                raise ValueError(
                    "FAILED recommendation must not include business gap payloads"
                )
            if self.confidence is not None:
                raise ValueError("FAILED recommendation must not include confidence")
        return self
