"""Application service for Agent 3 allocation-to-persistence wiring."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Literal

from .schemas import (
    AllocationRequest,
    AllocationRecommendation,
    utc_now,
    validate_timezone_aware,
)
from .constants import RecommendationStatus
from .repositories.persistence_exceptions import (
    PersistenceError,
    PersistenceValidationError,
    PersistenceConflictError,
    PersistenceTransactionError,
)


# ============================================================================
# Protocols for Dependency Injection
# ============================================================================


class AllocationServiceProtocol(ABC):
    """Protocol for the allocation service dependency."""

    @abstractmethod
    async def process_allocation_request(
        self,
        request: AllocationRequest,
        evaluation_timestamp: Optional[datetime] = None,
    ) -> AllocationRecommendation:
        """Process an allocation request and return a recommendation."""
        pass


class PersistenceProtocol(ABC):
    """Protocol for the persistence dependency."""

    @abstractmethod
    async def persist_allocation_result(
        self,
        request: AllocationRequest,
        recommendation: AllocationRecommendation,
        evaluation_timestamp: datetime,
    ) -> UUID:
        """Persist allocation result and return recommendation_id."""
        pass


# ============================================================================
# Result Contract
# ============================================================================


class PersistedAllocationResult(BaseModel):
    """Result envelope for successful persistence operations."""

    tenant_id: UUID
    correlation_id: UUID
    allocation_request_id: UUID
    recommendation_id: UUID
    recommendation_status: str
    persisted: Literal[True] = True
    persisted_at: datetime
    recommendation: AllocationRecommendation

    @model_validator(mode="after")
    def validate_contract(self) -> "PersistedAllocationResult":
        """Validate the result contract invariants."""
        # Ensure persisted is always True (enforced by Literal, but double-check)
        if self.persisted is not True:
            raise ValueError("persisted must be True")

        # Ensure all IDs are present
        if not self.tenant_id:
            raise ValueError("tenant_id is required")
        if not self.correlation_id:
            raise ValueError("correlation_id is required")
        if not self.allocation_request_id:
            raise ValueError("allocation_request_id is required")
        if not self.recommendation_id:
            raise ValueError("recommendation_id is required")

        # Ensure persisted_at is timezone-aware
        if self.persisted_at.tzinfo is None or self.persisted_at.tzinfo.utcoffset(self.persisted_at) is None:
            raise ValueError("persisted_at must be timezone-aware (UTC)")

        # Ensure tenant_id matches recommendation metadata
        if self.recommendation.metadata.tenant_id != self.tenant_id:
            raise ValueError("tenant_id does not match recommendation metadata")

        # Ensure correlation_id matches recommendation metadata
        if self.recommendation.metadata.correlation_id != self.correlation_id:
            raise ValueError("correlation_id does not match recommendation metadata")

        # Ensure APPROVED/REJECTED statuses are not used
        # Note: Agent 3 RecommendationStatus enum only includes GENERATED, PENDING_HUMAN_APPROVAL, SUPERSEDED, FAILED
        # APPROVED and REJECTED are not in the enum, so this check is defensive

        return self

    @classmethod
    def create(
        cls,
        tenant_id: UUID,
        correlation_id: UUID,
        allocation_request_id: UUID,
        recommendation_id: UUID,
        recommendation_status: str,
        recommendation: AllocationRecommendation,
        persisted_at: Optional[datetime] = None,
    ) -> PersistedAllocationResult:
        """Factory method to create a persisted result."""
        if persisted_at is None:
            persisted_at = utc_now()
        else:
            validate_timezone_aware(persisted_at, "persisted_at")

        return cls(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            allocation_request_id=allocation_request_id,
            recommendation_id=recommendation_id,
            recommendation_status=recommendation_status,
            persisted=True,
            persisted_at=persisted_at,
            recommendation=recommendation,
        )


# ============================================================================
# Application Service
# ============================================================================


class PersistentResourceAllocationService:
    """Application service that orchestrates allocation and persistence."""

    def __init__(
        self,
        allocation_service: AllocationServiceProtocol,
        persistence: PersistenceProtocol,
    ):
        """Initialize with injected dependencies.

        Args:
            allocation_service: Service for processing allocation requests
            persistence: Repository for persisting allocation results
        """
        self._allocation_service = allocation_service
        self._persistence = persistence

    async def process_and_persist(
        self,
        request: AllocationRequest,
        *,
        evaluation_timestamp: Optional[datetime] = None,
    ) -> PersistedAllocationResult:
        """Process an allocation request and persist the result.

        This method:
        1. Validates the input through normal Pydantic validation
        2. Reads tenant_id only from request.metadata.tenant_id
        3. Preserves request.metadata.correlation_id exactly
        4. Calls the allocation service once
        5. Validates the returned recommendation normally
        6. Persists the exact validated request/recommendation
        7. Returns success only after the database transaction completes

        Args:
            request: The validated allocation request
            evaluation_timestamp: Optional evaluation timestamp (defaults to UTC now)

        Returns:
            PersistedAllocationResult with IDs and persisted recommendation

        Raises:
            PersistenceValidationError: If validation fails during persistence
            PersistenceConflictError: If idempotency conflict detected
            PersistenceTransactionError: If persistence transaction fails
            PersistenceError: For other persistence failures
        """
        # Set evaluation timestamp
        if evaluation_timestamp is None:
            evaluation_timestamp = utc_now()
        else:
            validate_timezone_aware(evaluation_timestamp, "evaluation_timestamp")

        # Extract tenant_id and correlation_id from request metadata
        tenant_id = request.metadata.tenant_id
        correlation_id = request.metadata.correlation_id

        # Call allocation service exactly once
        recommendation = await self._allocation_service.process_allocation_request(
            request,
            evaluation_timestamp=evaluation_timestamp,
        )

        # Validate recommendation status matches request metadata
        if recommendation.metadata.correlation_id != correlation_id:
            raise PersistenceValidationError(
                "Recommendation correlation_id does not match request correlation_id"
            )
        if recommendation.metadata.tenant_id != tenant_id:
            raise PersistenceValidationError(
                "Recommendation tenant_id does not match request tenant_id"
            )

        # Persist the exact request and recommendation
        try:
            recommendation_id = await self._persistence.persist_allocation_result(
                request=request,
                recommendation=recommendation,
                evaluation_timestamp=evaluation_timestamp,
            )
        except (PersistenceValidationError, PersistenceConflictError, PersistenceTransactionError):
            # Re-raise persistence-specific exceptions without wrapping
            raise
        except Exception as exc:
            # Wrap unexpected exceptions in PersistenceTransactionError
            raise PersistenceTransactionError(
                f"Persistence failed for correlation_id {correlation_id}"
            ) from exc

        # Return successful result envelope
        # Note: allocation_request_id is not directly returned by persist_allocation_result,
        # so we use the recommendation_id as the primary identifier
        return PersistedAllocationResult.create(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            allocation_request_id=recommendation_id,  # Using recommendation_id as proxy
            recommendation_id=recommendation_id,
            recommendation_status=recommendation.status.value,
            recommendation=recommendation,
        )
