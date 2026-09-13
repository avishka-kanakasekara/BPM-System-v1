"""Company Policy & Knowledge Repository for Agent 4 governance."""

from .constants import (
    PolicyCategory,
    PolicyOperator,
    PolicyRetrievalStatus,
    PolicyRuleType,
    PolicyVersionStatus,
)
from .ingestion import PolicyIngestionService
from .repository import (
    InMemoryPolicyRepository,
    PolicyConflictError,
    PolicyNotFoundError,
    PolicyRepository,
    get_default_policy_repository,
    reset_default_policy_repository,
)
from .retrieval import PolicyRetrievalService
from .rule_extractor import chunk_text, extract_rules_from_text
from .schemas import (
    CompanyPolicyRecord,
    PolicyChunk,
    PolicyCreateRequest,
    PolicyDecisionPackage,
    PolicyEvidenceItem,
    PolicyRetrievalResult,
    PolicyRiskSnapshot,
    PolicyRule,
    PolicyVersionRecord,
)

__all__ = [
    "PolicyCategory",
    "PolicyOperator",
    "PolicyRetrievalStatus",
    "PolicyRuleType",
    "PolicyVersionStatus",
    "PolicyIngestionService",
    "InMemoryPolicyRepository",
    "PolicyConflictError",
    "PolicyNotFoundError",
    "PolicyRepository",
    "get_default_policy_repository",
    "reset_default_policy_repository",
    "PolicyRetrievalService",
    "chunk_text",
    "extract_rules_from_text",
    "CompanyPolicyRecord",
    "PolicyChunk",
    "PolicyCreateRequest",
    "PolicyDecisionPackage",
    "PolicyEvidenceItem",
    "PolicyRetrievalResult",
    "PolicyRiskSnapshot",
    "PolicyRule",
    "PolicyVersionRecord",
]
