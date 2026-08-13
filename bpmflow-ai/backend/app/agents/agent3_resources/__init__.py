# Agent 3: Workforce & Resource Allocation

from .constants import (
    ResourceType,
    ExclusionReason,
    RecommendationStatus,
    GapAlternativeType,
    GapType,
    MessageType,
    SCORING_WEIGHTS,
    MAX_EVIDENCE_AGE_DAYS,
    SCHEMA_VERSION,
    AGENT_3_SENDER,
    AGENT_4_RECEIVER,
    FailureErrorCode,
    FAILURE_RETRYABLE,
    ResourceLookupError,
)
from .schemas import (
    AgentMessageMetadata,
    HumanResourceRequirement,
    BudgetResourceRequirement,
    AllocationRequest,
    HumanResourceEvidence,
    BudgetResourceEvidence,
    ExclusionReasonEntry,
    ExcludedResource,
    ScoreBreakdown,
    RankedHumanCandidate,
    RankedCandidate,
    BudgetValidationResult,
    BudgetValidationChecks,
    RequirementResult,
    ResourceGap,
    ResourceAlternative,
    AllocationRecommendation,
    utc_now,
    validate_timezone_aware,
)
from .interfaces import ResourceRepository, InMemoryResourceRepository
from .retrieval import CandidateRetriever
from .eligibility import EligibilityEvaluator
from .ranking import HumanResourceRanker
from .gaps import GapDetector
from .explainer_template import TemplateExplainer, ExplanationContext
from .service import ResourceAllocationService
from .strategies import ResourceStrategy, HumanResourceStrategy, BudgetResourceStrategy
from .failures import (
    FailureSpec,
    detect_invalid_request,
    build_failed_recommendation,
    build_resource_lookup_failure,
    build_internal_error_failure,
    is_resource_lookup_error,
)
from .fixtures import (
    create_human_evidence,
    create_budget_evidence,
    create_human_requirement,
    create_budget_requirement,
    get_tenant_a_id,
    get_tenant_b_id,
    get_requester_id,
    get_resource_id_1,
    get_resource_id_2,
    get_resource_id_3,
)

__all__ = [
    # Constants
    "ResourceType",
    "ExclusionReason",
    "RecommendationStatus",
    "GapAlternativeType",
    "GapType",
    "MessageType",
    "SCORING_WEIGHTS",
    "MAX_EVIDENCE_AGE_DAYS",
    "SCHEMA_VERSION",
    "AGENT_3_SENDER",
    "AGENT_4_RECEIVER",
    "FailureErrorCode",
    "FAILURE_RETRYABLE",
    "ResourceLookupError",
    # Schemas
    "AgentMessageMetadata",
    "HumanResourceRequirement",
    "BudgetResourceRequirement",
    "AllocationRequest",
    "HumanResourceEvidence",
    "BudgetResourceEvidence",
    "ExclusionReasonEntry",
    "ExcludedResource",
    "ScoreBreakdown",
    "RankedHumanCandidate",
    "RankedCandidate",
    "BudgetValidationResult",
    "BudgetValidationChecks",
    "RequirementResult",
    "ResourceGap",
    "ResourceAlternative",
    "AllocationRecommendation",
    "utc_now",
    "validate_timezone_aware",
    # Interfaces
    "ResourceRepository",
    "InMemoryResourceRepository",
    # Core components
    "CandidateRetriever",
    "EligibilityEvaluator",
    "HumanResourceRanker",
    "GapDetector",
    "TemplateExplainer",
    "ExplanationContext",
    "ResourceAllocationService",
    "FailureSpec",
    "detect_invalid_request",
    "build_failed_recommendation",
    "build_resource_lookup_failure",
    "build_internal_error_failure",
    "is_resource_lookup_error",
    # Strategies
    "ResourceStrategy",
    "HumanResourceStrategy",
    "BudgetResourceStrategy",
    # Test fixtures
    "create_human_evidence",
    "create_budget_evidence",
    "create_human_requirement",
    "create_budget_requirement",
    "get_tenant_a_id",
    "get_tenant_b_id",
    "get_requester_id",
    "get_resource_id_1",
    "get_resource_id_2",
    "get_resource_id_3",
]
