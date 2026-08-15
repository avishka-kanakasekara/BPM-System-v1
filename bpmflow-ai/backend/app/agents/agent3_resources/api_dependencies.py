"""Agent 3-local API dependencies for trusted request context and service injection.

This module provides dependency contracts for FastAPI routes that ensure:
- Trusted tenant context from verified authentication (not request body)
- Proper dependency injection for services and repositories
- Production wiring with real Supabase JWT verification
- Test-friendly override mechanisms

Production authentication uses verified Supabase JWT tokens with JWKS verification.
Tenant ID is extracted from app_metadata.tenant_id (administratively controlled).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Set
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.core.security import VerifiedPrincipal, get_verified_principal
from app.core.database import get_session_factory


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
        - tenant_id comes from app_metadata.tenant_id (administratively controlled)
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
# Production Request Context Provider
# ============================================================================


class ProductionRequestContextProvider(RequestContextProtocol):
    """Production request context provider using verified Supabase JWT.

    This provider:
    - Uses verified principal from Supabase JWT verification
    - Extracts tenant_id from app_metadata.tenant_id
    - Maps verified claims to Agent3RequestContext
    - Fails closed on any verification error

    Tests should override this with a synthetic context provider.
    """

    def __init__(self, principal: VerifiedPrincipal):
        """Initialize with verified principal.

        Args:
            principal: The verified principal from JWT verification
        """
        self._principal = principal

    async def get_context(self) -> Agent3RequestContext:
        """Get the trusted request context from verified principal.

        Returns:
            Agent3RequestContext with verified tenant and actor information
        """
        return Agent3RequestContext(
            tenant_id=self._principal.tenant_id,
            actor_id=self._principal.user_id,
            roles=set(self._principal.roles),
            correlation_id=None,  # Correlation ID is request-specific, not from auth
        )


# ============================================================================
# Dependency Function
# ============================================================================


async def get_request_context(
    principal: VerifiedPrincipal = Depends(get_verified_principal),
) -> Agent3RequestContext:
    """FastAPI dependency to get trusted request context from verified JWT.

    This dependency:
    - Verifies JWT signature and claims via get_verified_principal
    - Extracts tenant_id from app_metadata.tenant_id
    - Returns Agent3RequestContext with verified tenant and actor information
    - Tests must override with a synthetic context provider

    Args:
        principal: The verified principal from JWT verification

    Returns:
        Agent3RequestContext with verified tenant and actor information

    Raises:
        HTTPException: 401 if token is invalid/expired
        HTTPException: 403 if tenant claim is missing/invalid
        HTTPException: 503 if JWKS fetch fails
    """
    provider = ProductionRequestContextProvider(principal)
    return await provider.get_context()


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
# Production Service Dependencies
# ============================================================================


async def get_allocation_service(
) -> AllocationServiceProtocol:
    """FastAPI dependency to get the real allocation service.

    This dependency:
    - Imports ResourceAllocationService lazily (not at import time)
    - Returns the real service for production use
    - Tests should override with a fake service

    Returns:
        ResourceAllocationService instance
    """
    from app.agents.agent3_resources.service import ResourceAllocationService
    from app.agents.agent3_resources.repositories.postgres_resource_repository import (
        PostgresResourceRepository,
    )

    # Get session factory lazily
    session_factory = get_session_factory()

    # Create resource repository with session factory
    resource_repository = PostgresResourceRepository(session_factory)

    # Create and return allocation service
    return ResourceAllocationService(resource_repository)


async def get_persistence_service(
) -> PersistenceProtocol:
    """FastAPI dependency to get the real persistence service.

    This dependency:
    - Imports RecommendationWriteRepository lazily (not at import time)
    - Returns the real repository for production use
    - Tests should override with a fake service

    Returns:
        RecommendationWriteRepository instance
    """
    from app.agents.agent3_resources.repositories.recommendation_repository import (
        RecommendationWriteRepository,
    )

    # Get session factory lazily
    session_factory = get_session_factory()

    # Create and return write repository
    return RecommendationWriteRepository(session_factory)


async def get_read_repository(
) -> ReadRepositoryProtocol:
    """FastAPI dependency to get the real read repository.

    This dependency:
    - Imports RecommendationWriteRepository lazily (not at import time)
    - Returns the real repository for production use
    - Tests should override with a fake repository

    Returns:
        RecommendationWriteRepository instance (has read methods)
    """
    from app.agents.agent3_resources.repositories.recommendation_repository import (
        RecommendationWriteRepository,
    )

    # Get session factory lazily
    session_factory = get_session_factory()

    # Create and return repository (has both read and write methods)
    return RecommendationWriteRepository(session_factory)
