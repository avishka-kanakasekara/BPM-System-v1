"""Pydantic schemas for Agent 4 workflow state management and risk analysis."""

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .constants import (
    HIGH_VALUE_PURCHASE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
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
