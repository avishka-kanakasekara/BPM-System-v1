"""Failure detection and FAILED recommendation construction for Agent 3."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .constants import ExclusionReason, FailureErrorCode, FAILURE_RETRYABLE
from .schemas import (
    AllocationRequest,
    AllocationRecommendation,
    AgentMessageMetadata,
    RequirementResult,
    RecommendationStatus,
)


@dataclass(frozen=True)
class FailureSpec:
    """Describes a plan-level allocation failure."""
    error_code: FailureErrorCode
    error_message: str

    @property
    def retryable(self) -> bool:
        return FAILURE_RETRYABLE[self.error_code]


def detect_invalid_request(
    request: AllocationRequest,
    evaluation_timestamp: datetime,
) -> Optional[FailureSpec]:
    """Detect semantically invalid requests that pass schema validation."""
    if request.human_requirements is None and request.budget_requirements is None:
        return FailureSpec(
            error_code=FailureErrorCode.INVALID_REQUEST,
            error_message="Request must include at least one resource requirement",
        )

    if request.human_requirements is not None:
        if request.human_requirements.task_deadline < evaluation_timestamp:
            return FailureSpec(
                error_code=FailureErrorCode.INVALID_REQUEST,
                error_message="Human resource task deadline is in the past",
            )

    if request.budget_requirements is not None:
        if request.budget_requirements.task_deadline < evaluation_timestamp:
            return FailureSpec(
                error_code=FailureErrorCode.INVALID_REQUEST,
                error_message="Budget resource task deadline is in the past",
            )

    return None


def _all_have_exclusion_reason(
    excluded_resources,
    reason: ExclusionReason,
) -> bool:
    """Return True when every excluded resource includes the given reason."""
    if not excluded_resources:
        return False
    return all(
        any(entry.reason == reason for entry in resource.exclusion_reasons)
        for resource in excluded_resources
    )


def detect_human_failure(
    human_result: Optional[RequirementResult],
) -> Optional[FailureSpec]:
    """Detect plan-level HUMAN allocation failures."""
    if human_result is None or human_result.eligible_candidates:
        return None

    excluded = human_result.excluded_resources

    if _all_have_exclusion_reason(excluded, ExclusionReason.MISSING_REQUIRED_EVIDENCE):
        return FailureSpec(
            error_code=FailureErrorCode.MISSING_REQUIRED_EVIDENCE,
            error_message=(
                "All candidates lack required availability or workload evidence; "
                "no candidate can be ranked"
            ),
        )

    if _all_have_exclusion_reason(
        excluded,
        ExclusionReason.SEGREGATION_OF_DUTIES_VIOLATION,
    ):
        return FailureSpec(
            error_code=FailureErrorCode.SOD_CONFLICT_UNRESOLVED,
            error_message=(
                "Segregation-of-duties conflict with no alternative candidate available"
            ),
        )

    return FailureSpec(
        error_code=FailureErrorCode.NO_ELIGIBLE_CANDIDATES,
        error_message=(
            "No eligible HUMAN candidates remain after eligibility filtering"
        ),
    )


def detect_budget_failure(
    budget_result: Optional[RequirementResult],
) -> Optional[FailureSpec]:
    """Detect plan-level BUDGET validation failures."""
    if budget_result is None:
        return None

    validation = budget_result.budget_validation
    if validation is None:
        return FailureSpec(
            error_code=FailureErrorCode.BUDGET_UNAVAILABLE,
            error_message="No budget resource available for validation",
        )

    checks = (
        validation.sufficient_balance,
        validation.cost_centre_match,
        validation.currency_match,
        validation.validity_period_valid,
        validation.within_authorization_limit,
    )
    if not all(checks):
        return FailureSpec(
            error_code=FailureErrorCode.BUDGET_UNAVAILABLE,
            error_message="Budget validation failed with no feasible fallback",
        )

    return None


def build_failed_recommendation(
    request_metadata: AgentMessageMetadata,
    response_metadata: AgentMessageMetadata,
    failure: FailureSpec,
) -> AllocationRecommendation:
    """Build a schema-valid FAILED recommendation without success payload."""
    return AllocationRecommendation(
        metadata=response_metadata,
        status=RecommendationStatus.FAILED,
        human_requirement_result=None,
        budget_requirement_result=None,
        resource_gaps=[],
        alternatives=[],
        explanation="",
        requires_human_approval=True,
        confidence=None,
        limitations=[failure.error_message],
        error_code=failure.error_code.value,
        error_message=failure.error_message,
        retryable=failure.retryable,
    )


def build_resource_lookup_failure(
    request_metadata: AgentMessageMetadata,
    response_metadata: AgentMessageMetadata,
    detail: str,
) -> AllocationRecommendation:
    """Build a FAILED recommendation for repository lookup errors."""
    failure = FailureSpec(
        error_code=FailureErrorCode.RESOURCE_LOOKUP_FAILED,
        error_message=f"Resource lookup failed: {detail}",
    )
    return build_failed_recommendation(request_metadata, response_metadata, failure)
