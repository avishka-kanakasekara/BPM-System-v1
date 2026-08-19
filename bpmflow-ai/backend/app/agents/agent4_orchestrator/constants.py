"""Constants for Agent 4 Orchestrator."""

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
