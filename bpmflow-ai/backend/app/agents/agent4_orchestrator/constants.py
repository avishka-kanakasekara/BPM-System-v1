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


class ExceptionStatus(str, Enum):
    """Statuses from public.exceptions comments: open, in_progress, resolved, ignored."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class ExceptionSeverity(str, Enum):
    """Severities from public.exceptions comments."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExceptionType(str, Enum):
    """Controlled exception codes. Legacy lowercase values remain valid."""

    TIMEOUT = "timeout"
    RESOURCE_CONFLICT = "resource_conflict"
    APPROVAL_DENIED = "approval_denied"
    SYSTEM_ERROR = "system_error"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    SOD_VIOLATION = "SOD_VIOLATION"
    NO_ELIGIBLE_RESOURCE = "NO_ELIGIBLE_RESOURCE"
    TOOL_FAILURE = "TOOL_FAILURE"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    INVOICE_MISMATCH = "INVOICE_MISMATCH"
    INVOICE_TOTAL_INVALID = "INVOICE_TOTAL_INVALID"
    VENDOR_MISMATCH = "VENDOR_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    WORKFLOW_FAILURE = "WORKFLOW_FAILURE"


def exception_type_from_code(code: str | None) -> ExceptionType:
    """Map a discrepancy/error code onto the controlled ExceptionType set."""
    raw = (code or "").strip()
    if not raw:
        return ExceptionType.SYSTEM_ERROR
    try:
        return ExceptionType(raw)
    except ValueError:
        pass
    aliases = {
        "MISSING_PO": ExceptionType.MISSING_EVIDENCE,
        "MISSING_INVOICE": ExceptionType.MISSING_EVIDENCE,
        "MISSING_PO_ITEM": ExceptionType.INVOICE_MISMATCH,
        "MISSING_INVOICE_ITEM": ExceptionType.INVOICE_MISMATCH,
        "UNIT_PRICE_MISMATCH": ExceptionType.AMOUNT_MISMATCH,
        "LINE_TOTAL_MISMATCH": ExceptionType.AMOUNT_MISMATCH,
        "INSUFFICIENT_BUDGET": ExceptionType.BUDGET_EXCEEDED,
        "SAME_PERSON": ExceptionType.SOD_VIOLATION,
        "INSUFFICIENT_EVIDENCE": ExceptionType.MISSING_EVIDENCE,
    }
    return aliases.get(raw.upper(), ExceptionType.WORKFLOW_FAILURE)


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
    APPROVAL_THRESHOLD = "APPROVAL_THRESHOLD"
    SLA_RISK = "SLA_RISK"
    POLICY_UNCERTAINTY = "POLICY_UNCERTAINTY"
    POLICY_CONFLICT = "POLICY_CONFLICT"


class RiskRecommendation(str, Enum):
    """Recommended control. Not an approval or stage-change decision."""

    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    REQUEST_EVIDENCE = "REQUEST_EVIDENCE"
    HUMAN_VERIFICATION = "HUMAN_VERIFICATION"
    REASSIGN_APPROVER = "REASSIGN_APPROVER"
    BLOCK_ACTION = "BLOCK_ACTION"
    CLARIFY_POLICY = "CLARIFY_POLICY"


# Higher number = more severe. Used only to compute overall_risk_level.
RISK_LEVEL_RANK = {
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}

# Legacy development default used ONLY when no PolicyRiskSnapshot is attached.
# Production risk review attaches tenant policy evidence and must not rely on this
# as the company's business rule.
HIGH_VALUE_PURCHASE_THRESHOLD = Decimal("10000.00")
LOW_CONFIDENCE_THRESHOLD = Decimal("0.70")

# Audit action labels for policy/risk events
AUDIT_POLICY_RETRIEVED = "POLICY_RETRIEVED"
AUDIT_RISK_ANALYSIS_STARTED = "RISK_ANALYSIS_STARTED"
AUDIT_RISK_IDENTIFIED = "RISK_IDENTIFIED"
AUDIT_POLICY_CONFLICT = "POLICY_CONFLICT"
AUDIT_POLICY_UNCERTAINTY = "POLICY_UNCERTAINTY"
AUDIT_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
AUDIT_EXECUTION_AUTHORIZED = "EXECUTION_AUTHORIZED"
AUDIT_EXECUTION_BLOCKED = "EXECUTION_BLOCKED"
