"""Enforce Agent 3 advisory-only contract in code."""

from __future__ import annotations

from .constants import RecommendationStatus
from .schemas import AllocationRecommendation

ADVISORY_ALLOWED_STATUSES = frozenset(
    {
        RecommendationStatus.GENERATED,
        RecommendationStatus.PENDING_HUMAN_APPROVAL,
        RecommendationStatus.SUPERSEDED,
        RecommendationStatus.FAILED,
    }
)

FORBIDDEN_DECISION_STATUSES = frozenset({"APPROVED", "REJECTED", "AUTO_ASSIGNED"})


class AdvisoryViolationError(ValueError):
    """Raised when a recommendation violates the advisory-only contract."""


def assert_advisory_recommendation(recommendation: AllocationRecommendation) -> None:
    """Ensure Agent 3 never auto-assigns or records approval decisions.

    Agent 3 produces advisory recommendations only. Human approval happens
    outside Agent 3 (typically Agent 4 / workflow orchestration).
    """
    status_value = recommendation.status.value
    if status_value in FORBIDDEN_DECISION_STATUSES:
        raise AdvisoryViolationError(
            f"Agent 3 cannot emit decision status {status_value}"
        )
    if recommendation.status not in ADVISORY_ALLOWED_STATUSES:
        raise AdvisoryViolationError(
            f"Agent 3 status {status_value} is not advisory-safe"
        )

    successful = recommendation.status in {
        RecommendationStatus.GENERATED,
        RecommendationStatus.PENDING_HUMAN_APPROVAL,
        RecommendationStatus.SUPERSEDED,
    }
    if successful and not recommendation.requires_human_approval:
        raise AdvisoryViolationError(
            "Successful Agent 3 recommendations must require human approval"
        )

    if getattr(recommendation, "assigned_resource_id", None) is not None:
        raise AdvisoryViolationError("Agent 3 must never auto-assign a resource")
