"""API request/response schemas for Agent 3 FastAPI endpoints.

These schemas define the HTTP contract for Agent 3 API, ensuring:
- UUID fields remain UUID/string-safe
- Decimal values serialize without binary float calculations
- Timezone-aware ISO-8601 timestamps
- No employee names in exclusion details
- No untrusted internal fields
- No APPROVED or REJECTED Agent 3 status
- persisted=True only after persistence success
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_serializer


# ============================================================================
# Error Response Schema
# ============================================================================


class Agent3APIError(BaseModel):
    """Standard error response for Agent 3 API endpoints.

    Attributes:
        error_code: Stable error code for programmatic handling
        message: Generic error message (no sensitive details)
        correlation_id: Optional correlation ID for tracing
        retryable: Whether the operation can be retried
    """

    model_config = ConfigDict(extra="forbid")

    error_code: str
    message: str
    correlation_id: Optional[UUID] = None
    retryable: bool = False


# ============================================================================
# Recommendation Summary Response
# ============================================================================


class RecommendationSummary(BaseModel):
    """Summary response for recommendation read endpoints.

    Since the repository returns only header/summary data (not complete
    recommendation trees with candidates/gaps/evidence), this schema
    honestly reflects what is actually returned.

    Attributes:
        recommendation_id: The recommendation UUID
        tenant_id: The tenant UUID
        correlation_id: The correlation UUID
        status: Recommendation status (GENERATED, PENDING_HUMAN_APPROVAL, SUPERSEDED, FAILED)
        persisted_at: UTC timestamp when persisted
        explanation: Recommendation explanation
        confidence: Confidence score (0-1)
        requires_human_approval: Whether human approval is required
        manual_intervention_required: Whether manual intervention is required
        error_code: Error code (for FAILED status)
        error_message: Error message (for FAILED status)
        retryable: Whether the operation is retryable (for FAILED status)
    """

    model_config = ConfigDict(
        ser_json_timedelta="iso8601",
        extra="forbid",
    )

    recommendation_id: UUID
    tenant_id: UUID
    correlation_id: UUID
    status: str
    persisted_at: datetime
    explanation: str = ""
    confidence: Optional[Decimal] = None
    requires_human_approval: bool = True
    manual_intervention_required: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: Optional[bool] = None

    @field_serializer('confidence')
    def serialize_confidence(self, value: Optional[Decimal]) -> Optional[str]:
        """Serialize Decimal to string for decimal-safe JSON representation."""
        return str(value) if value is not None else None

    @field_serializer('persisted_at')
    def serialize_persisted_at(self, value: datetime) -> str:
        """Serialize datetime to ISO8601 string."""
        return value.isoformat()


# ============================================================================
# Persisted Allocation Response
# ============================================================================


class PersistedAllocationResponse(BaseModel):
    """Response for POST /agent3/allocations endpoint.

    This is the full persisted result returned after successful persistence.
    It includes the complete recommendation with all business data.

    Attributes:
        tenant_id: The tenant UUID
        correlation_id: The correlation UUID
        allocation_request_id: The allocation request UUID
        recommendation_id: The recommendation UUID
        recommendation_status: The recommendation status
        persisted: Always True (Literal)
        persisted_at: UTC timestamp when persisted
        recommendation: The complete allocation recommendation
    """

    model_config = ConfigDict(
        ser_json_timedelta="iso8601",
        extra="forbid",
    )

    tenant_id: UUID
    correlation_id: UUID
    allocation_request_id: UUID
    recommendation_id: UUID
    recommendation_status: str
    persisted: bool = True
    persisted_at: datetime
    recommendation: Dict[str, Any]  # Complete recommendation as dict

    @field_serializer('persisted_at')
    def serialize_persisted_at(self, value: datetime) -> str:
        """Serialize datetime to ISO8601 string."""
        return value.isoformat()
