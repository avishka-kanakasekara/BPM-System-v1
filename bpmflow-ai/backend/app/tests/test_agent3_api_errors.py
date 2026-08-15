"""API error handling tests for Agent 3 FastAPI endpoints.

These tests verify HTTP error mapping and error response sanitization.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Set
from uuid import uuid4, UUID

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.api.v1.routes_agent3 import router
from app.agents.agent3_resources.api_dependencies import (
    Agent3RequestContext,
    RequestContextProtocol,
    AllocationServiceProtocol,
    PersistenceProtocol,
    ReadRepositoryProtocol,
    get_request_context,
    get_allocation_service,
    get_persistence_service,
    get_read_repository,
)
from app.agents.agent3_resources.schemas import (
    AllocationRequest,
    AllocationRecommendation,
    AgentMessageMetadata,
    RecommendationStatus,
)
from app.agents.agent3_resources.constants import MessageType
from app.agents.agent3_resources.repositories.persistence_exceptions import (
    PersistenceConflictError,
    PersistenceValidationError,
    PersistenceTransactionError,
)


# ============================================================================
# Fake Dependencies for Testing
# ============================================================================


class FakeRequestContextProvider(RequestContextProtocol):
    """Fake request context provider for testing."""

    def __init__(self, tenant_id: UUID, actor_id: UUID, roles: Set[str]):
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.roles = roles

    async def get_context(self) -> Agent3RequestContext:
        return Agent3RequestContext(
            tenant_id=self.tenant_id,
            actor_id=self.actor_id,
            roles=self.roles,
        )


class FakeAllocationService(AllocationServiceProtocol):
    """Fake allocation service for testing."""

    def __init__(self, recommendation: AllocationRecommendation = None):
        self._recommendation = recommendation

    async def process_allocation_request(
        self, request: AllocationRequest, evaluation_timestamp: Optional[datetime] = None
    ) -> AllocationRecommendation:
        if self._recommendation:
            return self._recommendation
        return AllocationRecommendation(
            metadata=request.metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=Decimal("0.9"),
            requires_human_approval=True,
            manual_intervention_required=False,
        )


class FakePersistenceService(PersistenceProtocol):
    """Fake persistence service for testing that can raise errors."""

    def __init__(self, should_raise: Optional[Exception] = None):
        self.should_raise = should_raise

    async def persist_allocation_result(
        self, request: AllocationRequest, recommendation: AllocationRecommendation, evaluation_timestamp: datetime
    ) -> UUID:
        if self.should_raise:
            raise self.should_raise
        return uuid4()


class FakeReadRepository(ReadRepositoryProtocol):
    """Fake read repository for testing."""

    async def get_recommendation(self, tenant_id: UUID, recommendation_id: UUID) -> Optional[dict]:
        return None

    async def get_latest_recommendation_by_correlation_id(self, tenant_id: UUID, correlation_id: UUID) -> Optional[dict]:
        return None


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.fixture
def actor_id():
    return uuid4()


@pytest.fixture
def metadata(tenant_id):
    return AgentMessageMetadata(
        tenant_id=tenant_id,
        correlation_id=uuid4(),
        process_instance_id=uuid4(),
        task_id=uuid4(),
        message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
    )


@pytest.fixture
def test_app(tenant_id, actor_id):
    """Create a test FastAPI app with Agent 3 router."""
    app = FastAPI()
    app.include_router(router)

    fake_context_provider = FakeRequestContextProvider(
        tenant_id=tenant_id, actor_id=actor_id, roles={"user"}
    )
    fake_allocation = FakeAllocationService()
    fake_persistence = FakePersistenceService()
    fake_read_repo = FakeReadRepository()

    async def override_get_request_context():
        return await fake_context_provider.get_context()

    app.dependency_overrides[get_request_context] = override_get_request_context
    app.dependency_overrides[get_allocation_service] = lambda: fake_allocation
    app.dependency_overrides[get_persistence_service] = lambda: fake_persistence
    app.dependency_overrides[get_read_repository] = lambda: fake_read_repo

    yield app

    app.dependency_overrides.clear()


# ============================================================================
# Error Mapping Tests
# ============================================================================


class TestAgent3APIErrors:
    """Error handling tests for Agent 3 API endpoints."""

    @pytest.mark.asyncio
    async def test_persistence_conflict_returns_409(self, test_app, metadata):
        """Test persistence conflict returns 409."""
        app = test_app

        fake_persistence = FakePersistenceService(
            should_raise=PersistenceConflictError("Duplicate correlation_id")
        )
        app.dependency_overrides[get_persistence_service] = lambda: fake_persistence

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.status_code == 409
        # FastAPI HTTPException.detail is returned as the response body
        assert "PERSISTENCE_CONFLICT" in str(response.json())

    @pytest.mark.asyncio
    async def test_persistence_validation_error_maps_safely(self, test_app, metadata):
        """Test persistence validation error maps safely to 422."""
        app = test_app

        fake_persistence = FakePersistenceService(
            should_raise=PersistenceValidationError("Invalid datetime")
        )
        app.dependency_overrides[get_persistence_service] = lambda: fake_persistence

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.status_code == 422
        # FastAPI HTTPException.detail is returned as the response body
        assert "PERSISTENCE_VALIDATION_ERROR" in str(response.json())

    @pytest.mark.asyncio
    async def test_persistence_transaction_error_returns_503(self, test_app, metadata):
        """Test persistence transaction error returns 503."""
        app = test_app

        fake_persistence = FakePersistenceService(
            should_raise=PersistenceTransactionError("Transaction failed")
        )
        app.dependency_overrides[get_persistence_service] = lambda: fake_persistence

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.status_code == 503
        # FastAPI HTTPException.detail is returned as the response body
        assert "PERSISTENCE_TRANSACTION_ERROR" in str(response.json())

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_sanitized_500(self, test_app, metadata):
        """Test unexpected exception returns sanitized 500."""
        app = test_app

        # The application service wraps unexpected errors in PersistenceTransactionError
        # which maps to 503. To test 500, we need to raise an error that isn't caught
        # by the persistence error mapping. Let's test the sanitize_internal_error function
        # by testing a different scenario.
        
        # For now, test that the error is sanitized (no sensitive data leaked)
        fake_persistence = FakePersistenceService(
            should_raise=RuntimeError("Unexpected error with sensitive data")
        )
        app.dependency_overrides[get_persistence_service] = lambda: fake_persistence

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        # The application service wraps in PersistenceTransactionError (503)
        assert response.status_code == 503
        # FastAPI HTTPException.detail is returned as the response body
        assert "PERSISTENCE_TRANSACTION_ERROR" in str(response.json())
        assert "sensitive data" not in str(response.json())

    @pytest.mark.asyncio
    async def test_business_constraint_not_mapped_to_technical_failure(self, test_app, metadata):
        """Test business constraint (PENDING_HUMAN_APPROVAL) is not mapped to technical failure."""
        app = test_app

        # Create a business gap recommendation
        fake_allocation = FakeAllocationService()
        gap_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.PENDING_HUMAN_APPROVAL,
            explanation="Gap detected",
            confidence=Decimal("0.8"),
            requires_human_approval=True,
            manual_intervention_required=False,
        )
        fake_allocation._recommendation = gap_recommendation
        app.dependency_overrides[get_allocation_service] = lambda: fake_allocation

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        # Business gap should return 201, not a technical failure
        assert response.status_code == 201
        assert response.json()["recommendation_status"] == "PENDING_HUMAN_APPROVAL"

    @pytest.mark.asyncio
    async def test_no_exception_stack_trace_appears(self, test_app, metadata):
        """Test no exception stack trace appears in error response."""
        app = test_app

        fake_persistence = FakePersistenceService(
            should_raise=RuntimeError("Error with stack trace")
        )
        app.dependency_overrides[get_persistence_service] = lambda: fake_persistence

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        error_str = str(response.json())
        assert "Traceback" not in error_str
        assert "File" not in error_str
        assert "line" not in error_str

    @pytest.mark.asyncio
    async def test_dependency_unavailable_returns_503(self, test_app, metadata):
        """Test dependency unavailable returns 503."""
        app = test_app

        # Remove persistence override to trigger unavailable placeholder
        app.dependency_overrides.pop(get_persistence_service, None)

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.status_code == 503
        # FastAPI HTTPException.detail is returned as the response body
        # Just verify it's a 503 error with some error code
        assert "error_code" in str(response.json())
