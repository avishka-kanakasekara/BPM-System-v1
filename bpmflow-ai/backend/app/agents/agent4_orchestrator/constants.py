"""Constants for Agent 4 Orchestrator."""

from decimal import Decimal
from enum import Enum


class WorkflowStage(str, Enum):
    """BPM workflow stages owned by Agent 4."""

    DRAFT = "DRAFT"
    DISCOVERING = "DISCOVERING"
    RESOURCE_PLANNING = "RESOURCE_PLANNING"
    RISK_REVIEW = "RISK_REVIEW"
    AWAITING_HUMAN_APPROVAL = "AWAITING_HUMAN_APPROVAL"
    WORKFLOW_EXECUTION = "WORKFLOW_EXECUTION"
    INVOICE_MATCHING = "INVOICE_MATCHING"
    EXCEPTION = "EXCEPTION"
    COMPLETED = "COMPLETED"


class ApprovalStatus(str, Enum):
    """Human approval-request lifecycle statuses."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class RiskLevel(str, Enum):
    """Risk severity used for approval routing and exception handling."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskType(str, Enum):
    """Deterministic risk categories identified by Agent 4."""

    HIGH_VALUE_PURCHASE = "HIGH_VALUE_PURCHASE"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    SEGREGATION_OF_DUTIES = "SEGREGATION_OF_DUTIES"
    UNAUTHORIZED_ACTION = "UNAUTHORIZED_ACTION"
    BUDGET_VALIDATION_FAILURE = "BUDGET_VALIDATION_FAILURE"


class RiskRecommendation(str, Enum):
    """Recommended control. Not an approval or stage-change decision."""

    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    REQUEST_EVIDENCE = "REQUEST_EVIDENCE"
    HUMAN_VERIFICATION = "HUMAN_VERIFICATION"
    REASSIGN_APPROVER = "REASSIGN_APPROVER"
    BLOCK_ACTION = "BLOCK_ACTION"


# Higher number = more severe. Used only to compute overall_risk_level.
RISK_LEVEL_RANK = {
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}

# Demo/development defaults. Not production procurement policy.
# Override per evaluation via RiskEvaluationContext.
HIGH_VALUE_PURCHASE_THRESHOLD = Decimal("10000.00")
LOW_CONFIDENCE_THRESHOLD = Decimal("0.70")
