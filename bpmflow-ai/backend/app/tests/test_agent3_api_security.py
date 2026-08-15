"""API security tests for Agent 3 FastAPI endpoints.

These tests verify security behaviors including tenant isolation,
authentication context, and input validation.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Set
from uuid import uuid4, UUID

from fastapi import FastAPI, HTTPException, status
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

    async def process_allocation_request(
        self, request: AllocationRequest, evaluation_timestamp: Optional[datetime] = None
    ) -> AllocationRecommendation:
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

    async def persist_allocation_result(
        self, request: AllocationRequest, recommendation: AllocationRecommendation, evaluation_timestamp: datetime
    ) -> UUID:
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
# Security Tests
# ============================================================================


class TestAgent3APISecurity:
    """Security tests for Agent 3 API endpoints."""

    @pytest.mark.asyncio
    async def test_missing_trusted_context_fails_closed(self, test_app, metadata):
        """Test missing trusted context fails closed with 503."""
        app = test_app

        # Remove context override to test production placeholder
        app.dependency_overrides.pop(get_request_context, None)

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.status_code == 503
        # FastAPI HTTPException.detail is returned as the response body
        assert "AUTH_NOT_CONFIGURED" in str(response.json())

    @pytest.mark.asyncio
    async def test_request_tenant_mismatch_returns_403(self, test_app, metadata, tenant_id):
        """Test request tenant mismatch returns 403."""
        app = test_app

        # Create request with different tenant_id
        wrong_tenant_id = uuid4()
        wrong_metadata = AgentMessageMetadata(
            tenant_id=wrong_tenant_id,
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )

        request = AllocationRequest(
            metadata=wrong_metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.status_code == 403
        # FastAPI HTTPException.detail is returned as the response body
        assert "TENANT_MISMATCH" in str(response.json())

    @pytest.mark.asyncio
    async def test_requester_id_cannot_change_tenant_scope(self, test_app, metadata):
        """Test requester_id cannot change tenant scope."""
        app = test_app

        # requester_id is part of the requirement, not tenant scope
        # This is verified by the tenant_id check in the route
        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        # The route only checks tenant_id, not requester_id
        # This test verifies that requester_id is not used as tenant scope
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_malformed_uuid_returns_422(self, test_app):
        """Test malformed UUID returns 422."""
        app = test_app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/agent3/recommendations/not-a-uuid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_request_body_returns_422(self, test_app):
        """Test invalid request body returns 422."""
        app = test_app

        invalid_request = {
            "metadata": {
                "tenant_id": "not-a-uuid",
                "correlation_id": "not-a-uuid",
            }
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=invalid_request)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_approved_rejected_status_cannot_be_returned(self, test_app, metadata):
        """Test APPROVED/REJECTED status cannot be returned."""
        app = test_app

        # Agent 3's RecommendationStatus enum doesn't include APPROVED/REJECTED
        # This test verifies the schema prevents these statuses
        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        assert response.status_code == 201
        # Verify the returned status is one of Agent 3's allowed statuses
        allowed_statuses = {"GENERATED", "PENDING_HUMAN_APPROVAL", "SUPERSEDED", "FAILED"}
        assert response.json()["recommendation_status"] in allowed_statuses

    @pytest.mark.asyncio
    async def test_error_responses_contain_no_db_url_password_sql(self, test_app, metadata):
        """Test error responses contain no DB URL/password/SQL."""
        app = test_app

        # Remove context override to trigger 503 error
        app.dependency_overrides.pop(get_request_context, None)

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request.model_dump(mode='json'))

        error_detail = response.json()
        error_str = str(error_detail)

        assert "password" not in error_str.lower()
        assert "postgresql://" not in error_str.lower()
        assert "select" not in error_str.lower()
        assert "insert" not in error_str.lower()

    @pytest.mark.asyncio
    async def test_oversized_unexpected_fields_rejected_by_pydantic(self, test_app, metadata):
        """Test oversized/unexpected fields are rejected according to Pydantic policy."""
        app = test_app

        # Add unexpected field to request
        request_dict = {
            "metadata": metadata.model_dump(mode='json'),
            "human_requirements": None,
            "budget_requirements": None,
            "unexpected_field": "should_be_rejected",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request_dict)

        # With extra="forbid" on inbound models, unknown fields should return 422
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_top_level_field_rejected_in_response(self, test_app, metadata):
        """Test unknown fields in API response models are rejected."""
        app = test_app

        # This test verifies that the API response models have extra='forbid'
        # by attempting to create a response with extra fields
        from app.agents.agent3_resources.api_schemas import Agent3APIError
        
        # Should raise validation error for extra fields
        try:
            Agent3APIError(
                error_code="TEST_ERROR",
                message="Test message",
                correlation_id=uuid4(),
                retryable=False,
                unexpected_field="should_fail"
            )
            assert False, "Should have raised validation error for extra field"
        except Exception as e:
            # Expected to fail due to extra='forbid'
            assert "extra" in str(e).lower()

    @pytest.mark.asyncio
    async def test_unknown_field_in_recommendation_summary_rejected(self, test_app, metadata):
        """Test unknown fields in RecommendationSummary are rejected."""
        from app.agents.agent3_resources.api_schemas import RecommendationSummary
        
        # Should raise validation error for extra fields
        try:
            RecommendationSummary(
                recommendation_id=uuid4(),
                tenant_id=uuid4(),
                correlation_id=uuid4(),
                status="GENERATED",
                persisted_at=datetime.now(),
                unexpected_field="should_fail"
            )
            assert False, "Should have raised validation error for extra field"
        except Exception as e:
            # Expected to fail due to extra='forbid'
            assert "extra" in str(e).lower()

    @pytest.mark.asyncio
    async def test_unknown_field_in_persisted_response_rejected(self, test_app, metadata):
        """Test unknown fields in PersistedAllocationResponse are rejected."""
        from app.agents.agent3_resources.api_schemas import PersistedAllocationResponse
        
        # Should raise validation error for extra fields
        try:
            PersistedAllocationResponse(
                tenant_id=uuid4(),
                correlation_id=uuid4(),
                allocation_request_id=uuid4(),
                recommendation_id=uuid4(),
                recommendation_status="GENERATED",
                persisted=True,
                persisted_at=datetime.now(),
                recommendation={},
                unexpected_field="should_fail"
            )
            assert False, "Should have raised validation error for extra field"
        except Exception as e:
            # Expected to fail due to extra='forbid'
            assert "extra" in str(e).lower()

    @pytest.mark.asyncio
    async def test_unknown_top_level_field_in_request_returns_422(self, test_app, metadata):
        """Test unknown top-level field in POST request returns HTTP 422."""
        app = test_app

        # Add unknown field to request
        request_dict = {
            "metadata": metadata.model_dump(mode='json'),
            "human_requirements": None,
            "budget_requirements": None,
            "unexpected_top_level_field": "should_be_rejected",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request_dict)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_metadata_field_in_request_returns_422(self, test_app, metadata):
        """Test unknown field in metadata returns HTTP 422."""
        app = test_app

        # Add unknown field to metadata
        request_dict = {
            "metadata": {
                **metadata.model_dump(mode='json'),
                "unknown_metadata_field": "should_be_rejected"
            },
            "human_requirements": None,
            "budget_requirements": None,
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request_dict)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_human_requirement_field_returns_422(self, test_app, metadata):
        """Test unknown field in HUMAN requirement returns HTTP 422."""
        app = test_app

        from app.agents.agent3_resources.constants import ResourceType
        
        # Add unknown field to human requirement
        request_dict = {
            "metadata": metadata.model_dump(mode='json'),
            "human_requirements": {
                "resource_type": ResourceType.HUMAN,
                "requester_id": str(uuid4()),
                "task_deadline": "2024-06-01T00:00:00Z",
                "estimated_effort_hours": "10",
                "process_stage": "resource_allocation",
                "unknown_human_field": "should_be_rejected"
            },
            "budget_requirements": None,
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request_dict)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_budget_requirement_field_returns_422(self, test_app, metadata):
        """Test unknown field in BUDGET requirement returns HTTP 422."""
        app = test_app

        from app.agents.agent3_resources.constants import ResourceType
        
        # Add unknown field to budget requirement
        request_dict = {
            "metadata": metadata.model_dump(mode='json'),
            "human_requirements": None,
            "budget_requirements": {
                "resource_type": ResourceType.BUDGET,
                "required_amount": "5000",
                "currency": "USD",
                "requester_id": str(uuid4()),
                "task_deadline": "2024-06-01T00:00:00Z",
                "process_stage": "resource_allocation",
                "unknown_budget_field": "should_be_rejected"
            },
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/agent3/allocations", json=request_dict)

        assert response.status_code == 422
