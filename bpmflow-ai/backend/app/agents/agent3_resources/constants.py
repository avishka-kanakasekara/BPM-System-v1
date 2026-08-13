"""Constants for Agent 3 Resource Allocation."""

from enum import Enum


class ResourceType(str, Enum):
    """Resource types supported by Agent 3."""
    HUMAN = "HUMAN"
    BUDGET = "BUDGET"
    SYSTEM = "SYSTEM"
    EQUIPMENT = "EQUIPMENT"
    EXTERNAL_SERVICE = "EXTERNAL_SERVICE"


class ExclusionReason(str, Enum):
    """Hard exclusion reasons for HUMAN resources."""
    INACTIVE_RESOURCE = "INACTIVE_RESOURCE"
    REQUIRED_ROLE_MISSING = "REQUIRED_ROLE_MISSING"
    MANDATORY_SKILL_MISSING = "MANDATORY_SKILL_MISSING"
    REQUIRED_AUTHORITY_MISSING = "REQUIRED_AUTHORITY_MISSING"
    UNAVAILABLE_BEFORE_DEADLINE = "UNAVAILABLE_BEFORE_DEADLINE"
    PROJECTED_WORKLOAD_EXCEEDED = "PROJECTED_WORKLOAD_EXCEEDED"
    SEGREGATION_OF_DUTIES_VIOLATION = "SEGREGATION_OF_DUTIES_VIOLATION"
    REQUESTER_SELF_APPROVAL = "REQUESTER_SELF_APPROVAL"
    CONFLICT_OF_INTEREST = "CONFLICT_OF_INTEREST"
    MISSING_REQUIRED_EVIDENCE = "MISSING_REQUIRED_EVIDENCE"
    STALE_EVIDENCE = "STALE_EVIDENCE"


class RecommendationStatus(str, Enum):
    """Statuses owned by Agent 3."""
    GENERATED = "GENERATED"
    PENDING_HUMAN_APPROVAL = "PENDING_HUMAN_APPROVAL"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"


class GapAlternativeType(str, Enum):
    """Resource gap alternatives in exact required order."""
    RELAX_NON_MANDATORY_PREFERENCES = "RELAX_NON_MANDATORY_PREFERENCES"
    REBALANCE_WORKLOAD = "REBALANCE_WORKLOAD"
    RESCHEDULE_DEADLINE = "RESCHEDULE_DEADLINE"
    TEMPORARY_INTERNAL_SUPPORT = "TEMPORARY_INTERNAL_SUPPORT"
    TRAIN_OR_UPSKILL = "TRAIN_OR_UPSKILL"
    APPROVED_EXTERNAL_SERVICE = "APPROVED_EXTERNAL_SERVICE"
    RECRUITMENT_ESCALATION = "RECRUITMENT_ESCALATION"


class GapType(str, Enum):
    """Business constraint gap types for completed analyses."""
    NO_ELIGIBLE_HUMAN = "NO_ELIGIBLE_HUMAN"
    MISSING_REQUIRED_EVIDENCE = "MISSING_REQUIRED_EVIDENCE"
    SOD_CONFLICT_UNRESOLVED = "SOD_CONFLICT_UNRESOLVED"
    BUDGET_UNAVAILABLE = "BUDGET_UNAVAILABLE"
    WORKLOAD_CAPACITY = "WORKLOAD_CAPACITY"
    UNAVAILABLE_RESOURCES = "UNAVAILABLE_RESOURCES"


class MessageType(str, Enum):
    """Message types for inter-agent communication."""
    RESOURCE_ALLOCATION_REQUEST = "RESOURCE_ALLOCATION_REQUEST"
    RESOURCE_ALLOCATION_RESPONSE = "RESOURCE_ALLOCATION_RESPONSE"


class FailureErrorCode(str, Enum):
    """Technical failure codes returned when analysis cannot complete."""
    INVALID_REQUEST = "INVALID_REQUEST"
    RESOURCE_LOOKUP_FAILED = "RESOURCE_LOOKUP_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


FAILURE_RETRYABLE: dict[FailureErrorCode, bool] = {
    FailureErrorCode.INVALID_REQUEST: False,
    FailureErrorCode.RESOURCE_LOOKUP_FAILED: True,
    FailureErrorCode.INTERNAL_ERROR: True,
}


class ResourceLookupError(Exception):
    """Raised when repository or database retrieval fails."""


# Scoring formula weights (must sum to 1.0)
SCORING_WEIGHTS = {
    "role_match": 0.30,
    "skill_match": 0.25,
    "availability_score": 0.20,
    "workload_fit": 0.15,
    "authority_match": 0.10,
}

# Evidence freshness: maximum age in days
MAX_EVIDENCE_AGE_DAYS = 90

# Schema version for message contract
SCHEMA_VERSION = "1.0.0"

# Agent identifiers
AGENT_3_SENDER = "agent3"
AGENT_4_RECEIVER = "agent4"
