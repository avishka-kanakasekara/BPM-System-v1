"""API contract tests for Agent 3 FastAPI endpoints.

These tests verify the API contract matches the specification.
"""

import os
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Set
from uuid import uuid4, UUID

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

# Set minimal environment variables for config
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from app.api.v1.routes_agent3 import router

from app.agents.agent3_resources.schemas import (
    AllocationRequest,
    AgentMessageMetadata,
    HumanResourceRequirement,
    BudgetResourceRequirement,
    AllocationRecommendation,
    RecommendationStatus,
    MessageType,
)
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
from app.agents.agent3_resources.constants import ResourceType


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
        self.call_count = 0

    async def process_allocation_request(
        self, request: AllocationRequest, evaluation_timestamp: Optional[datetime] = None
    ) -> AllocationRecommendation:
        self.call_count += 1
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
    """Fake persistence service for testing."""

    def __init__(self, recommendation_id: UUID):
        self._recommendation_id = recommendation_id
        self.call_count = 0

    async def persist_allocation_result(
        self, request: AllocationRequest, recommendation: AllocationRecommendation, evaluation_timestamp: datetime
    ) -> UUID:
        self.call_count += 1
        return self._recommendation_id


class FakeReadRepository(ReadRepositoryProtocol):
    """Fake read repository for testing."""

    def __init__(self, data: Optional[dict] = None):
        self._data = data
        self.last_tenant_id = None
        self.last_recommendation_id = None
        self.last_correlation_id = None

    async def get_recommendation(self, tenant_id: UUID, recommendation_id: UUID) -> Optional[dict]:
        self.last_tenant_id = tenant_id
        self.last_recommendation_id = recommendation_id
        return self._data

    async def get_latest_recommendation_by_correlation_id(self, tenant_id: UUID, correlation_id: UUID) -> Optional[dict]:
        self.last_tenant_id = tenant_id
        self.last_correlation_id = correlation_id
        return self._data


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
def successful_recommendation(metadata):
    return AllocationRecommendation(
        metadata=metadata,
        status=RecommendationStatus.GENERATED,
        explanation="Test explanation",
        confidence=Decimal("0.9"),
        requires_human_approval=True,
        manual_intervention_required=False,
    )


@pytest.fixture
def human_requirement(tenant_id):
    return HumanResourceRequirement(
        resource_type=ResourceType.HUMAN,
        requester_id=uuid4(),
        task_deadline=datetime(2024, 6, 1, tzinfo=timezone.utc),
        estimated_effort_hours=Decimal("10"),
        process_stage="resource_allocation",
        required_roles=["developer"],
        mandatory_skills=["python"],
    )


@pytest.fixture
def budget_requirement(tenant_id):
    return BudgetResourceRequirement(
        resource_type=ResourceType.BUDGET,
        requester_id=uuid4(),
        task_deadline=datetime(2024, 6, 1, tzinfo=timezone.utc),
        required_amount=Decimal("5000"),
        currency="USD",
        process_stage="resource_allocation",
    )


@pytest.fixture
def test_app(tenant_id, actor_id, successful_recommendation):
    """Create a test FastAPI app with Agent 3 router."""
    app = FastAPI()
    app.include_router(router)

    # Override dependencies with fakes
    recommendation_id = uuid4()
    fake_context_provider = FakeRequestContextProvider(
        tenant_id=tenant_id, actor_id=actor_id, roles={"user"}
    )
    fake_allocation = FakeAllocationService(successful_recommendation)
    fake_persistence = FakePersistenceService(recommendation_id)
    fake_read_repo = FakeReadRepository()

    async def override_get_request_context():
        return await fake_context_provider.get_context()

    app.dependency_overrides[get_request_context] = override_get_request_context
    app.dependency_overrides[get_allocation_service] = lambda: fake_allocation
    app.dependency_overrides[get_persistence_service] = lambda: fake_persistence
    app.dependency_overrides[get_read_repository] = lambda: fake_read_repo

    yield app, fake_allocation, fake_persistence, fake_read_repo, recommendation_id

    app.dependency_overrides.clear()


# ============================================================================
# POST /agent3/allocations Contract Tests
# ============================================================================


class TestPostAllocationsContract:
    """Contract tests for POST /agent3/allocations endpoint."""

    @pytest.mark.asyncio
    async def test_valid_human_request_returns_201(
        self, test_app, metadata, human_requirement, tenant_id
    ):
        """Test valid HUMAN request returns 201."""
        app, fake_allocation, fake_persistence, _, recommendation_id = test_app

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_requirement,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.status_code == 201
        assert response.json()["tenant_id"] == str(tenant_id)
        assert response.json()["persisted"] is True
        assert fake_allocation.call_count == 1
        assert fake_persistence.call_count == 1

    @pytest.mark.asyncio
    async def test_valid_budget_request_returns_201(
        self, test_app, metadata, budget_requirement, tenant_id
    ):
        """Test valid BUDGET request returns 201."""
        app, fake_allocation, fake_persistence, _, recommendation_id = test_app

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=budget_requirement,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.status_code == 201
        assert response.json()["tenant_id"] == str(tenant_id)
        assert fake_allocation.call_count == 1
        assert fake_persistence.call_count == 1

    @pytest.mark.asyncio
    async def test_mixed_human_budget_request_returns_201(
        self, test_app, metadata, human_requirement, budget_requirement, tenant_id
    ):
        """Test mixed HUMAN+BUDGET request returns 201."""
        app, fake_allocation, fake_persistence, _, recommendation_id = test_app

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_requirement,
            budget_requirements=budget_requirement,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.status_code == 201
        assert response.json()["tenant_id"] == str(tenant_id)
        assert fake_allocation.call_count == 1
        assert fake_persistence.call_count == 1

    @pytest.mark.asyncio
    async def test_business_gap_result_returns_201(self, test_app, metadata, tenant_id):
        """Test business gap result returns 201/PENDING_HUMAN_APPROVAL."""
        app, fake_allocation, fake_persistence, _, recommendation_id = test_app

        gap_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.PENDING_HUMAN_APPROVAL,
            explanation="Gap detected",
            confidence=Decimal("0.8"),
            requires_human_approval=True,
            manual_intervention_required=False,
        )

        fake_allocation._recommendation = gap_recommendation

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.status_code == 201
        assert response.json()["recommendation_status"] == "PENDING_HUMAN_APPROVAL"

    @pytest.mark.asyncio
    async def test_failed_recommendation_persists_and_returns_defined_behavior(
        self, test_app, metadata, tenant_id
    ):
        """Test schema-valid FAILED recommendation persists and returns defined API behavior."""
        app, fake_allocation, fake_persistence, _, recommendation_id = test_app

        failed_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.FAILED,
            explanation="",
            requires_human_approval=False,
            manual_intervention_required=True,
            error_code="TEST_ERROR",
            error_message="Test error message",
            retryable=True,
        )

        fake_allocation._recommendation = failed_recommendation

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.status_code == 201
        assert response.json()["recommendation_status"] == "FAILED"

    @pytest.mark.asyncio
    async def test_application_service_called_exactly_once(self, test_app, metadata):
        """Test application service called exactly once."""
        app, fake_allocation, fake_persistence, _, _ = test_app

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert fake_allocation.call_count == 1

    @pytest.mark.asyncio
    async def test_returned_persisted_ids_come_from_service(self, test_app, metadata):
        """Test returned persisted IDs come from service."""
        app, fake_allocation, fake_persistence, _, recommendation_id = test_app

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.json()["recommendation_id"] == str(recommendation_id)

    @pytest.mark.asyncio
    async def test_correlation_id_preserved_in_body(self, test_app, metadata):
        """Test correlation ID preserved in response body."""
        app, fake_allocation, fake_persistence, _, _ = test_app

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.json()["correlation_id"] == str(metadata.correlation_id)

    @pytest.mark.asyncio
    async def test_decimal_values_serialize_as_strings(self, test_app, metadata):
        """Test Decimal values serialize as strings, not floats, for decimal safety."""
        app, fake_allocation, fake_persistence, _, _ = test_app

        # Test various Decimal values for precision preservation
        # Note: confidence field has constraint <= 1, so we test valid range values
        test_decimals = [
            Decimal("0.1"),
            Decimal("0.8750"),
            Decimal("0.9999"),
        ]

        for test_decimal in test_decimals:
            # Create a recommendation with the test Decimal value
            from app.agents.agent3_resources.schemas import AllocationRecommendation, RecommendationStatus
            
            precise_recommendation = AllocationRecommendation(
                metadata=metadata,
                status=RecommendationStatus.GENERATED,
                explanation="Test",
                confidence=test_decimal,
                requires_human_approval=True,
                manual_intervention_required=False,
            )
            fake_allocation._recommendation = precise_recommendation

            request = AllocationRequest(
                metadata=metadata,
                human_requirements=None,
                budget_requirements=None,
            )

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

            # Verify confidence is serialized as a string, not a float
            confidence_value = response.json()["recommendation"]["confidence"]
            assert isinstance(confidence_value, str), f"Expected string for {test_decimal}, got {type(confidence_value)}"
            assert confidence_value == str(test_decimal), f"Expected '{test_decimal}', got '{confidence_value}'"


# ============================================================================
# GET /agent3/recommendations Contract Tests
# ============================================================================


class TestGetRecommendationsContract:
    """Contract tests for GET recommendation endpoints."""

    @pytest.mark.asyncio
    async def test_recommendation_found_for_same_tenant_returns_200(self, test_app, tenant_id):
        """Test recommendation found for same tenant returns 200."""
        app, _, _, fake_read_repo, _ = test_app

        recommendation_id = uuid4()
        correlation_id = uuid4()

        fake_read_repo._data = {
            "recommendation_id": str(recommendation_id),
            "tenant_id": str(tenant_id),
            "correlation_id": str(correlation_id),
            "status": "GENERATED",
            "persisted_at": datetime.now(timezone.utc).isoformat(),
            "explanation": "Test",
            "confidence": 0.9,
            "requires_human_approval": True,
            "manual_intervention_required": False,
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/agent3/recommendations/{recommendation_id}")

        assert response.status_code == 200
        assert response.json()["recommendation_id"] == str(recommendation_id)
        assert fake_read_repo.last_tenant_id == tenant_id

    @pytest.mark.asyncio
    async def test_missing_recommendation_returns_404(self, test_app):
        """Test missing recommendation returns 404."""
        app, _, _, fake_read_repo, _ = test_app

        fake_read_repo._data = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/agent3/recommendations/{uuid4()}")

        assert response.status_code == 404
        # FastAPI HTTPException.detail is returned as the response body
        assert "RECOMMENDATION_NOT_FOUND" in str(response.json())

    @pytest.mark.asyncio
    async def test_cross_tenant_recommendation_returns_404(self, test_app, tenant_id):
        """Test cross-tenant recommendation returns 404, not 403."""
        app, _, _, fake_read_repo, _ = test_app

        # Repository returns None for cross-tenant (simulated by returning None)
        fake_read_repo._data = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/agent3/recommendations/{uuid4()}")

        assert response.status_code == 404  # Not 403

    @pytest.mark.asyncio
    async def test_latest_by_correlation_returns_correct_version(self, test_app, tenant_id):
        """Test latest by correlation returns correct version."""
        app, _, _, fake_read_repo, _ = test_app

        correlation_id = uuid4()
        recommendation_id = uuid4()

        fake_read_repo._data = {
            "recommendation_id": str(recommendation_id),
            "tenant_id": str(tenant_id),
            "correlation_id": str(correlation_id),
            "status": "GENERATED",
            "persisted_at": datetime.now(timezone.utc).isoformat(),
            "explanation": "Test",
            "confidence": 0.9,
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/agent3/recommendations/by-correlation/{correlation_id}")

        assert response.status_code == 200
        assert response.json()["correlation_id"] == str(correlation_id)
        assert fake_read_repo.last_correlation_id == correlation_id

    @pytest.mark.asyncio
    async def test_repository_receives_trusted_tenant_id(self, test_app, tenant_id):
        """Test repository receives trusted tenant_id."""
        app, _, _, fake_read_repo, _ = test_app

        recommendation_id = uuid4()
        fake_read_repo._data = {
            "recommendation_id": str(recommendation_id),
            "tenant_id": str(tenant_id),
            "correlation_id": str(uuid4()),
            "status": "GENERATED",
            "persisted_at": datetime.now(timezone.utc).isoformat(),
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get(f"/agent3/recommendations/{recommendation_id}")

        assert fake_read_repo.last_tenant_id == tenant_id
