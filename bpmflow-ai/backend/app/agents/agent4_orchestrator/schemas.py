"""Pydantic schemas for Agent 4 workflow state management and risk analysis."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

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

    Thresholds default to demo values in constants.py and can be overridden
    per call without changing rule code.
    """

    purchase_amount: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    required_evidence: List[str] = Field(default_factory=list)
    provided_evidence: List[str] = Field(default_factory=list)
    confidence: Optional[Decimal] = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    requester_id: Optional[UUID] = None
    approver_id: Optional[UUID] = None
    unauthorized_action: bool = False
    budget_validation_failed: bool = False
    high_value_threshold: Decimal = Field(
        default=HIGH_VALUE_PURCHASE_THRESHOLD,
        ge=Decimal("0"),
    )
    low_confidence_threshold: Decimal = Field(
        default=LOW_CONFIDENCE_THRESHOLD,
        ge=Decimal("0"),
        le=Decimal("1"),
    )


class RiskFinding(BaseModel):
    """A single identified risk. Does not approve or reject the process."""

    risk_detected: bool = True
    risk_level: RiskLevel
    risk_type: RiskType
    description: str = Field(min_length=1)
    recommendation: RiskRecommendation


class RiskAssessment(BaseModel):
    """Complete deterministic risk result for one process/context."""

    risk_detected: bool
    overall_risk_level: Optional[RiskLevel] = None
    findings: List[RiskFinding] = Field(default_factory=list)


class ApprovalRequestRecord(BaseModel):
    """Approval gate record matching public.approval_requests."""

    id: UUID
    process_id: UUID
    task_id: Optional[UUID] = None
    requested_by: Optional[UUID] = None
    approver_id: Optional[UUID] = None
    status: ApprovalStatus
    risk_level: RiskLevel
    reason: str = Field(min_length=1)
    decision: Optional[ApprovalStatus] = None
    comments: Optional[str] = None
    created_at: datetime
    decided_at: Optional[datetime] = None


class ApprovalDecisionResult(BaseModel):
    """Outcome of approve_request or reject_request. No further workflow move."""

    approval: ApprovalRequestRecord
    decision: ApprovalStatus


class ApprovalGateResult(BaseModel):
    """Result of applying risk findings to the human-approval gate."""

    human_approval_required: bool
    approval: Optional[ApprovalRequestRecord] = None
    transition: Optional[ProcessStateTransition] = None


class ExceptionRecord(BaseModel):
    """BPM exception matching public.exceptions columns."""

    id: UUID
    process_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    severity: ExceptionSeverity
    type: ExceptionType
    description: str = Field(min_length=1)
    status: ExceptionStatus
    assigned_to: Optional[UUID] = None
    resolution_notes: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None


class WorkflowResult(BaseModel):
    """Outcome of one Agent 4 orchestration step. Not a DB row."""

    process_id: UUID
    current_stage: WorkflowStage
    success: bool
    message: str = Field(min_length=1)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    eligible_for_execution: bool = False
    human_approval_required: bool = False
    approval: Optional[ApprovalRequestRecord] = None
    risk_assessment: Optional[RiskAssessment] = None
    bpm_exception: Optional[ExceptionRecord] = None
