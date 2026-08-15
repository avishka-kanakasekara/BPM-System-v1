"""Agent 3 FastAPI routes for workforce and resource allocation.

This module provides HTTP endpoints for Agent 3 allocation operations:
- POST /agent3/allocations - Submit allocation request and persist result
- GET /agent3/recommendations/{recommendation_id} - Retrieve recommendation by ID
- GET /agent3/recommendations/by-correlation/{correlation_id} - Retrieve latest by correlation

Security:
- All endpoints require trusted tenant context from authentication
- Request body tenant_id must match trusted context tenant_id
- Cross-tenant access returns 404 (not 403 to avoid information leakage)
- Trusted-context tenant matching is implemented
- Production JWT authentication and RLS tenant policies remain pending

Error Mapping:
- 201: allocation calculated and persisted
- 400: semantic request error not covered by Pydantic
- 401: missing/invalid authenticated context
- 403: trusted tenant differs from request tenant
- 404: recommendation not found
- 409: PersistenceConflictError/idempotency conflict
- 422: FastAPI/Pydantic validation error
- 503: DB/session/application dependency unavailable
- 500: unexpected sanitized internal error

Testing:
- Fake-dependency API component tests are implemented
- These are not real database integration tests
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.responses import JSONResponse

from app.agents.agent3_resources.api_dependencies import (
    get_request_context,
    get_allocation_service,
    get_persistence_service,
    get_read_repository,
    Agent3RequestContext,
    AllocationServiceProtocol,
    PersistenceProtocol,
    ReadRepositoryProtocol,
)
from app.agents.agent3_resources.api_schemas import (
    Agent3APIError,
    PersistedAllocationResponse,
    RecommendationSummary,
)
from app.agents.agent3_resources.schemas import AllocationRequest
from app.agents.agent3_resources.repositories.persistence_exceptions import (
    PersistenceValidationError,
    PersistenceConflictError,
    PersistenceTransactionError,
    PersistenceError,
)


# ============================================================================
# Router Configuration
# ============================================================================

router = APIRouter(
    prefix="/agent3",
    tags=["Agent 3 - Workforce & Resource Allocation"],
)


# ============================================================================
# HTTP Error Mapping Helpers
# ============================================================================


def map_persistence_error_to_http(exc: PersistenceError, correlation_id: Optional[UUID]) -> HTTPException:
    """Map persistence exceptions to HTTP responses.

    Args:
        exc: The persistence exception
        correlation_id: Optional correlation ID for error response

    Returns:
        HTTPException with appropriate status code and sanitized error details
    """
    if isinstance(exc, PersistenceConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "PERSISTENCE_CONFLICT",
                "message": "A recommendation already exists for this correlation ID",
                "correlation_id": str(correlation_id) if correlation_id else None,
                "retryable": False,
            },
        )
    elif isinstance(exc, PersistenceValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error_code": "PERSISTENCE_VALIDATION_ERROR",
                "message": "Invalid data for persistence",
                "correlation_id": str(correlation_id) if correlation_id else None,
                "retryable": False,
            },
        )
    elif isinstance(exc, PersistenceTransactionError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "PERSISTENCE_TRANSACTION_ERROR",
                "message": "Persistence operation failed",
                "correlation_id": str(correlation_id) if correlation_id else None,
                "retryable": True,
            },
        )
    else:
        # Generic persistence error
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "PERSISTENCE_ERROR",
                "message": "Persistence operation failed",
                "correlation_id": str(correlation_id) if correlation_id else None,
                "retryable": True,
            },
        )


def sanitize_internal_error(exc: Exception, correlation_id: Optional[UUID]) -> HTTPException:
    """Create a sanitized 500 error response.

    Never returns exception str(), SQL, DB host, DB URL, password, or stack trace.

    Args:
        exc: The internal exception
        correlation_id: Optional correlation ID for error response

    Returns:
        HTTPException with sanitized error details
    """
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "error_code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "correlation_id": str(correlation_id) if correlation_id else None,
            "retryable": False,
        },
    )


# ============================================================================
# POST /agent3/allocations
# ============================================================================


@router.post(
    "/allocations",
    status_code=status.HTTP_201_CREATED,
    response_model=PersistedAllocationResponse,
    responses={
        status.HTTP_403_FORBIDDEN: {"model": Agent3APIError},
        status.HTTP_409_CONFLICT: {"model": Agent3APIError},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": Agent3APIError},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Agent3APIError},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": Agent3APIError},
    },
)
async def create_allocation(
    request: AllocationRequest,
    context: Agent3RequestContext = Depends(get_request_context),
    allocation_service: AllocationServiceProtocol = Depends(get_allocation_service),
    persistence_service: PersistenceProtocol = Depends(get_persistence_service),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID"),
):
    """Submit an allocation request and persist the result.

    This endpoint:
    - Validates the AllocationRequest through Pydantic
    - Compares request.metadata.tenant_id with trusted context tenant_id
    - Calls PersistentResourceAllocationService.process_and_persist exactly once
    - Returns persisted result only after DB persistence succeeds

    Business gap recommendations (PENDING_HUMAN_APPROVAL) return HTTP 201,
    not HTTP failure. Agent 3 remains advisory and never approves/rejects.

    Args:
        request: The allocation request
        context: Trusted request context with verified tenant_id
        allocation_service: Injected allocation service
        persistence_service: Injected persistence service
        x_correlation_id: Optional correlation ID from header

    Returns:
        PersistedAllocationResponse with persisted result

    Raises:
        HTTPException: 403 if tenant mismatch
        HTTPException: 409 if idempotency conflict
        HTTPException: 422 if validation error
        HTTPException: 503 if service unavailable
        HTTPException: 500 if unexpected error
    """
    # Validate tenant_id matches trusted context
    if request.metadata.tenant_id != context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "TENANT_MISMATCH",
                "message": "Request tenant_id does not match authenticated tenant",
                "correlation_id": str(request.metadata.correlation_id),
                "retryable": False,
            },
        )

    correlation_id = request.metadata.correlation_id

    try:
        # Import here to avoid circular dependency with application_service
        from app.agents.agent3_resources.application_service import (
            PersistentResourceAllocationService,
        )

        # Create application service with injected dependencies
        app_service = PersistentResourceAllocationService(
            allocation_service=allocation_service,
            persistence=persistence_service,
        )

        # Process and persist
        result = await app_service.process_and_persist(request)

        # Convert to API response
        return PersistedAllocationResponse(
            tenant_id=result.tenant_id,
            correlation_id=result.correlation_id,
            allocation_request_id=result.allocation_request_id,
            recommendation_id=result.recommendation_id,
            recommendation_status=result.recommendation_status,
            persisted=result.persisted,
            persisted_at=result.persisted_at,
            recommendation=result.recommendation.model_dump(),
        )

    except (PersistenceValidationError, PersistenceConflictError, PersistenceTransactionError) as exc:
        # Map persistence errors to HTTP responses
        raise map_persistence_error_to_http(exc, correlation_id)
    except Exception as exc:
        # Sanitize unexpected errors
        raise sanitize_internal_error(exc, correlation_id)


# ============================================================================
# GET /agent3/recommendations/by-correlation/{correlation_id}
# ============================================================================


@router.get(
    "/recommendations/by-correlation/{correlation_id}",
    response_model=RecommendationSummary,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": Agent3APIError},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Agent3APIError},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": Agent3APIError},
    },
)
async def get_recommendation_by_correlation(
    correlation_id: UUID,
    context: Agent3RequestContext = Depends(get_request_context),
    read_repository: ReadRepositoryProtocol = Depends(get_read_repository),
):
    """Get the latest recommendation by correlation ID.

    This endpoint:
    - Always filters using trusted tenant_id from context
    - Returns 404 when not found (including cross-tenant requests)
    - Never accepts tenant_id as a query parameter
    - Preserves deterministic latest/version behavior

    Cross-tenant requests return 404 (not 403) to avoid information leakage.

    Args:
        correlation_id: The correlation UUID
        context: Trusted request context with verified tenant_id
        read_repository: Injected read repository

    Returns:
        RecommendationSummary with recommendation header data

    Raises:
        HTTPException: 404 if not found
        HTTPException: 503 if service unavailable
        HTTPException: 500 if unexpected error
    """
    try:
        result = await read_repository.get_latest_recommendation_by_correlation_id(
            tenant_id=context.tenant_id,
            correlation_id=correlation_id,
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error_code": "RECOMMENDATION_NOT_FOUND",
                    "message": "No recommendation found for this correlation ID",
                    "correlation_id": str(correlation_id),
                    "retryable": False,
                },
            )

        # Convert repository dict to summary response
        return RecommendationSummary(
            recommendation_id=UUID(result["recommendation_id"]),
            tenant_id=UUID(result["tenant_id"]),
            correlation_id=UUID(result["correlation_id"]),
            status=result["status"],
            persisted_at=result["persisted_at"],
            explanation=result.get("explanation", ""),
            confidence=result.get("confidence"),
            requires_human_approval=result.get("requires_human_approval", True),
            manual_intervention_required=result.get("manual_intervention_required", False),
            error_code=result.get("error_code"),
            error_message=result.get("error_message"),
            retryable=result.get("retryable"),
        )

    except HTTPException:
        # Re-raise HTTP exceptions (404, etc.)
        raise
    except Exception as exc:
        # Sanitize unexpected errors
        raise sanitize_internal_error(exc, correlation_id)


# ============================================================================
# GET /agent3/recommendations/{recommendation_id}
# ============================================================================


@router.get(
    "/recommendations/{recommendation_id}",
    response_model=RecommendationSummary,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": Agent3APIError},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Agent3APIError},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": Agent3APIError},
    },
)
async def get_recommendation(
    recommendation_id: UUID,
    context: Agent3RequestContext = Depends(get_request_context),
    read_repository: ReadRepositoryProtocol = Depends(get_read_repository),
):
    """Get a recommendation by ID.

    This endpoint:
    - Always filters using trusted tenant_id from context
    - Returns 404 when not found (including cross-tenant requests)
    - Never accepts tenant_id as a query parameter

    Cross-tenant requests return 404 (not 403) to avoid information leakage.

    Args:
        recommendation_id: The recommendation UUID
        context: Trusted request context with verified tenant_id
        read_repository: Injected read repository

    Returns:
        RecommendationSummary with recommendation header data

    Raises:
        HTTPException: 404 if not found
        HTTPException: 503 if service unavailable
        HTTPException: 500 if unexpected error
    """
    try:
        result = await read_repository.get_recommendation(
            tenant_id=context.tenant_id,
            recommendation_id=recommendation_id,
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error_code": "RECOMMENDATION_NOT_FOUND",
                    "message": "Recommendation not found",
                    "correlation_id": None,
                    "retryable": False,
                },
            )

        # Convert repository dict to summary response
        return RecommendationSummary(
            recommendation_id=UUID(result["recommendation_id"]),
            tenant_id=UUID(result["tenant_id"]),
            correlation_id=UUID(result["correlation_id"]),
            status=result["status"],
            persisted_at=result["persisted_at"],
            explanation=result.get("explanation", ""),
            confidence=result.get("confidence"),
            requires_human_approval=result.get("requires_human_approval", True),
            manual_intervention_required=result.get("manual_intervention_required", False),
            error_code=result.get("error_code"),
            error_message=result.get("error_message"),
            retryable=result.get("retryable"),
        )

    except HTTPException:
        # Re-raise HTTP exceptions (404, etc.)
        raise
    except Exception as exc:
        # Sanitize unexpected errors
        raise sanitize_internal_error(exc, None)
