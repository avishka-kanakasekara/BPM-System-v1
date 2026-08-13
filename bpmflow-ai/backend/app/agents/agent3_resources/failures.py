"""Technical failure detection and FAILED recommendation construction."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Type, Tuple

from .constants import FailureErrorCode, FAILURE_RETRYABLE, ResourceLookupError
from .schemas import (
    AllocationRequest,
    AllocationRecommendation,
    AgentMessageMetadata,
    RecommendationStatus,
)

RESOURCE_LOOKUP_EXCEPTIONS: Tuple[Type[BaseException], ...] = (
    ResourceLookupError,
    ConnectionError,
    OSError,
)

INTERNAL_ERROR_MESSAGE = (
    "An internal processing error occurred. "
    "Reference the correlation ID for audit and support."
)


@dataclass(frozen=True)
class FailureSpec:
    """Describes a technical failure preventing analysis completion."""
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


def build_failed_recommendation(
    response_metadata: AgentMessageMetadata,
    failure: FailureSpec,
) -> AllocationRecommendation:
    """Build a schema-valid FAILED recommendation without business payload."""
    return AllocationRecommendation(
        metadata=response_metadata,
        status=RecommendationStatus.FAILED,
        human_requirement_result=None,
        budget_requirement_result=None,
        resource_gaps=[],
        alternatives=[],
        explanation="",
        requires_human_approval=False,
        manual_intervention_required=True,
        confidence=None,
        limitations=[],
        error_code=failure.error_code.value,
        error_message=failure.error_message,
        retryable=failure.retryable,
    )


def build_resource_lookup_failure(
    response_metadata: AgentMessageMetadata,
    detail: str,
) -> AllocationRecommendation:
    """Build a FAILED recommendation for repository lookup errors."""
    failure = FailureSpec(
        error_code=FailureErrorCode.RESOURCE_LOOKUP_FAILED,
        error_message=f"Resource lookup failed: {detail}",
    )
    return build_failed_recommendation(response_metadata, failure)


def build_internal_error_failure(
    response_metadata: AgentMessageMetadata,
) -> AllocationRecommendation:
    """Build a FAILED recommendation for unexpected internal errors."""
    failure = FailureSpec(
        error_code=FailureErrorCode.INTERNAL_ERROR,
        error_message=INTERNAL_ERROR_MESSAGE,
    )
    return build_failed_recommendation(response_metadata, failure)


def is_resource_lookup_error(exc: BaseException) -> bool:
    """Return True when an exception represents a resource lookup failure."""
    return isinstance(exc, RESOURCE_LOOKUP_EXCEPTIONS)
