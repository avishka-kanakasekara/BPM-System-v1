"""Pydantic schemas for Agent 4 workflow state management and risk analysis."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.policy_knowledge.schemas import PolicyDecisionPackage, PolicyRiskSnapshot

from .constants import (
    HIGH_VALUE_PURCHASE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
    ApprovalStatus,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    RiskLevel,
    RiskRecommendation,
    RiskType,
    WorkflowStage,
)


class ProcessStateTransition(BaseModel):
    """A requested BPM workflow stage change for a process."""

    process_id: UUID
    from_stage: WorkflowStage
    to_stage: WorkflowStage
    reason: str = Field(min_length=1)


class RiskEvaluationContext(BaseModel):
    """Structured process facts for deterministic risk analysis.

    When ``policy_snapshot`` is unset, legacy configurable thresholds apply
    (unit tests / callers that do not integrate the policy repository).

    When ``policy_snapshot`` is set, purchase thresholds and decision-critical
    policy uncertainty come from that tenant policy evidence — not from the
    hardcoded legacy default.
    """

    purchase_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    currency: str | None = None
    required_evidence: list[str] = Field(default_factory=list)
    provided_evidence: list[str] = Field(default_factory=list)
    confidence: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    requester_id: UUID | None = None
    approver_id: UUID | None = None
    requester_roles: list[str] = Field(default_factory=list)
    unauthorized_action: bool = False
    budget_validation_failed: bool = False
    available_budget: Decimal | None = Field(default=None, ge=Decimal("0"))
    process_age_hours: Decimal | None = Field(default=None, ge=Decimal("0"))
    high_value_threshold: Decimal = Field(
        default=HIGH_VALUE_PURCHASE_THRESHOLD,
        ge=Decimal("0"),
    )
    low_confidence_threshold: Decimal = Field(
        default=LOW_CONFIDENCE_THRESHOLD,
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    policy_snapshot: PolicyRiskSnapshot | None = None


class RiskFinding(BaseModel):
    """A single identified risk. Does not approve or reject the process."""

    risk_detected: bool = True
    risk_level: RiskLevel
    risk_type: RiskType
    description: str = Field(min_length=1)
    recommendation: RiskRecommendation
    evidence_refs: list[str] = Field(default_factory=list)
    policy_version: str | None = None
    amount: Decimal | None = None
    threshold: Decimal | None = None
    currency: str | None = None


class RiskAssessment(BaseModel):
    """Complete deterministic risk result for one process/context."""

    risk_detected: bool
    overall_risk_level: RiskLevel | None = None
    findings: list[RiskFinding] = Field(default_factory=list)
    policy_snapshot: PolicyRiskSnapshot | None = None


class ApprovalRequestRecord(BaseModel):
    """Approval gate record matching public.approval_requests."""

    id: UUID
    process_id: UUID
    task_id: UUID | None = None
    requested_by: UUID | None = None
    approver_id: UUID | None = None
    status: ApprovalStatus
    risk_level: RiskLevel
    reason: str = Field(min_length=1)
    decision: ApprovalStatus | None = None
    comments: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class ApprovalDecisionResult(BaseModel):
    """Outcome of approve_request or reject_request. No further workflow move."""

    approval: ApprovalRequestRecord
    decision: ApprovalStatus


class ApprovalGateResult(BaseModel):
    """Result of applying risk findings to the human-approval gate."""

    human_approval_required: bool
    approval: ApprovalRequestRecord | None = None
    transition: ProcessStateTransition | None = None


class ExceptionRecord(BaseModel):
    """BPM exception matching public.exceptions columns."""

    id: UUID
    process_id: UUID | None = None
    task_id: UUID | None = None
    tenant_id: UUID | None = None
    workflow_plan_id: UUID | None = None
    workflow_step_id: UUID | None = None
    exception_code: str | None = None
    title: str | None = None
    severity: ExceptionSeverity
    type: ExceptionType
    description: str = Field(min_length=1)
    status: ExceptionStatus
    assigned_to: UUID | None = None
    assigned_employee_id: UUID | None = None
    resolved_by_employee_id: UUID | None = None
    source_agent: str | None = None
    source_operation: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)
    resolution_notes: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    resolved_at: datetime | None = None


class WorkflowResult(BaseModel):
    """Outcome of one Agent 4 orchestration step. Not a DB row."""

    process_id: UUID
    current_stage: WorkflowStage
    success: bool
    message: str = Field(min_length=1)
    error_code: str | None = None
    error_message: str | None = None
    eligible_for_execution: bool = False
    human_approval_required: bool = False
    approval: ApprovalRequestRecord | None = None
    risk_assessment: RiskAssessment | None = None
    policy_decision: PolicyDecisionPackage | None = None
    bpm_exception: ExceptionRecord | None = None
    # Payload returned by the downstream agent for this step (e.g. Agent 3
    # recommendation or Agent 2 execution receipt summary).
    agent_response: dict | None = None
