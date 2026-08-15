"""Agent 3-local API dependencies for trusted request context and service injection.

This module provides dependency contracts for FastAPI routes that ensure:
- Trusted tenant context from verified authentication (not request body)
- Proper dependency injection for services and repositories
- Fail-closed behavior until production auth is wired
- Test-friendly override mechanisms

Production authentication/JWT wiring is pending group coordination.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Set
from uuid import UUID

from fastapi import Depends, HTTPException, status


# ============================================================================
# Trusted Request Context Contract
# ============================================================================


class Agent3RequestContext:
    """Trusted request context from verified authentication.

    Attributes:
        tenant_id: Verified tenant ID from authentication context
        actor_id: Verified actor/user ID from authentication context
        roles: Set of roles assigned to the actor
        correlation_id: Optional correlation ID from request headers

    Rules:
        - tenant_id MUST come from verified auth context, never request body
        - Request body tenant_id must match this tenant_id (403 if mismatch)
        - requester_id is never used as tenant scope
        - Production auth/JWT wiring is pending group coordination
    """

    def __init__(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        roles: Set[str],
        correlation_id: Optional[UUID] = None,
    ):
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.roles = roles
        self.correlation_id = correlation_id


class RequestContextProtocol(ABC):
    """Protocol for request context dependency."""

    @abstractmethod
    async def get_context(self) -> Agent3RequestContext:
        """Get the trusted request context."""
        pass


# ============================================================================
# Production Placeholder (Fails Closed)
# ============================================================================


class ProductionRequestContextProvider(RequestContextProtocol):
    """Production request context provider - fails closed until wired.

    This is a placeholder that returns HTTP 503 until group coordination
    completes the production authentication/JWT wiring.

    Tests should override this with a synthetic context provider.
    """

    async def get_context(self) -> Agent3RequestContext:
        """Fail closed - production auth not yet wired."""
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "AUTH_NOT_CONFIGURED",
                "message": "Authentication context not available. "
                "Production JWT wiring is pending group coordination.",
                "retryable": False,
            },
        )


# ============================================================================
# Dependency Function
# ============================================================================


async def get_request_context(
    context_provider: RequestContextProtocol = Depends(
        lambda: ProductionRequestContextProvider()
    ),
) -> Agent3RequestContext:
    """FastAPI dependency to get trusted request context.

    This dependency:
    - Returns verified tenant_id from authentication context
    - Fails closed with HTTP 503 until production auth is wired
    - Tests must override with a synthetic context provider

    Args:
        context_provider: The context provider (injected, overrideable in tests)

    Returns:
        Agent3RequestContext with verified tenant and actor information

    Raises:
        HTTPException: 503 if production auth is not configured
    """
    return await context_provider.get_context()


# ============================================================================
# Service Dependency Protocols
# ============================================================================


class AllocationServiceProtocol(ABC):
    """Protocol for allocation service dependency injection."""

    @abstractmethod
    async def process_allocation_request(
        self,
        request,
        evaluation_timestamp: Optional,
    ):
        """Process allocation request."""
        pass


class PersistenceProtocol(ABC):
    """Protocol for persistence dependency injection."""

    @abstractmethod
    async def persist_allocation_result(
        self,
        request,
        recommendation,
        evaluation_timestamp,
    ) -> UUID:
        """Persist allocation result."""
        pass


class ReadRepositoryProtocol(ABC):
    """Protocol for read repository dependency injection."""

    @abstractmethod
    async def get_recommendation(
        self,
        tenant_id: UUID,
        recommendation_id: UUID,
    ):
        """Get recommendation by ID."""
        pass

    @abstractmethod
    async def get_latest_recommendation_by_correlation_id(
        self,
        tenant_id: UUID,
        correlation_id: UUID,
    ):
        """Get latest recommendation by correlation ID."""
        pass


# ============================================================================
# Production Service Placeholders (Fail Closed)
# ============================================================================


class UnavailableAllocationService(AllocationServiceProtocol):
    """Placeholder allocation service - fails closed."""

    async def process_allocation_request(self, request, evaluation_timestamp: Optional):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "SERVICE_UNAVAILABLE",
                "message": "Allocation service not configured.",
                "retryable": False,
            },
        )


class UnavailablePersistenceService(PersistenceProtocol):
    """Placeholder persistence service - fails closed."""

    async def persist_allocation_result(
        self, request, recommendation, evaluation_timestamp
    ) -> UUID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "PERSISTENCE_UNAVAILABLE",
                "message": "Persistence service not configured.",
                "retryable": False,
            },
        )


class UnavailableReadRepository(ReadRepositoryProtocol):
    """Placeholder read repository - fails closed."""

    async def get_recommendation(self, tenant_id: UUID, recommendation_id: UUID):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "REPOSITORY_UNAVAILABLE",
                "message": "Read repository not configured.",
                "retryable": False,
            },
        )

    async def get_latest_recommendation_by_correlation_id(
        self, tenant_id: UUID, correlation_id: UUID
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "REPOSITORY_UNAVAILABLE",
                "message": "Read repository not configured.",
                "retryable": False,
            },
        )


# ============================================================================
# Service Dependency Functions
# ============================================================================


async def get_allocation_service(
    service: AllocationServiceProtocol = Depends(lambda: UnavailableAllocationService()),
) -> AllocationServiceProtocol:
    """FastAPI dependency to get allocation service.

    Tests should override with the real ResourceAllocationService.
    """
    return service


async def get_persistence_service(
    service: PersistenceProtocol = Depends(lambda: UnavailablePersistenceService()),
) -> PersistenceProtocol:
    """FastAPI dependency to get persistence service.

    Tests should override with the real RecommendationWriteRepository.
    """
    return service


async def get_read_repository(
    repository: ReadRepositoryProtocol = Depends(lambda: UnavailableReadRepository()),
) -> ReadRepositoryProtocol:
    """FastAPI dependency to get read repository.

    Tests should override with the real RecommendationWriteRepository.
    """
    return repository
