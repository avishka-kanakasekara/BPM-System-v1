"""Canonical tenant-scoped process business context (Phase 1).

ProcessContext is the source of truth for amount, currency, budget,
quotations, requester identity, evidence, and designated approver.
It does not own current_stage (Agent 4) and does not approve.
"""

from .exceptions import MissingRequiredContextError
from .identity import IdentityLink, resolve_employee_resource_id
from .schemas import (
    ApproverIdentity,
    BudgetFacts,
    DiscoverySummary,
    EvidenceItem,
    FactSource,
    PolicyRefs,
    ProcessContext,
    PurchaseFacts,
    PurchaseItem,
    QuotationFact,
    RequesterIdentity,
    RiskSnapshot,
)
from .service import (
    apply_verified_patch,
    context_from_process_row,
    empty_process_context,
    merge_process_context,
    require_fields,
)

__all__ = [
    "ApproverIdentity",
    "BudgetFacts",
    "DiscoverySummary",
    "EvidenceItem",
    "FactSource",
    "IdentityLink",
    "MissingRequiredContextError",
    "PolicyRefs",
    "ProcessContext",
    "PurchaseFacts",
    "PurchaseItem",
    "QuotationFact",
    "RequesterIdentity",
    "RiskSnapshot",
    "apply_verified_patch",
    "context_from_process_row",
    "empty_process_context",
    "merge_process_context",
    "require_fields",
    "resolve_employee_resource_id",
]
