"""Idempotency tests for Agent 3 write-path persistence."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import MagicMock

from app.agents.agent3_resources.repositories.recommendation_repository import (
    RecommendationWriteRepository,
)
from app.agents.agent3_resources.repositories.persistence_exceptions import (
    PersistenceConflictError,
)
from app.agents.agent3_resources.schemas import (
    AllocationRequest,
    AllocationRecommendation,
    HumanResourceRequirement,
    RequirementResult,
    AgentMessageMetadata,
    RecommendationStatus,
    ResourceType,
)


class FakeAsyncSession:
    """Fake AsyncSession for idempotency testing."""

    def __init__(self, existing_request=None, existing_recommendation=None, existing_requirements=None):
        self.committed = False
        self.rolled_back = False
        self.existing_request = existing_request
        self.existing_recommendation = existing_recommendation
        self.existing_requirements = existing_requirements  # List of (id, resource_type, sequence_order)
        self.executed_statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def execute(self, statement, params=None):
        self.executed_statements.append((statement, params))
        result = MagicMock()

        # Return existing request/recommendation if set
        if "SELECT id, tenant_id, correlation_id" in str(statement):
            if self.existing_request:
                # Return a proper row-like object with _mapping
                row = MagicMock()
                row._mapping = {
                    "id": self.existing_request[0],
                    "tenant_id": self.existing_request[1],
                    "correlation_id": self.existing_request[2],
                }
                result.fetchone.return_value = row
            else:
                result.fetchone.return_value = None
        elif "SELECT id" in str(statement) and "allocation_recommendations" in str(statement):
            if self.existing_recommendation:
                # Return a proper row-like object with _mapping
                row = MagicMock()
                row._mapping = {
                    "id": self.existing_recommendation[0],
                }
                result.fetchone.return_value = row
            else:
                result.fetchone.return_value = None
        elif "SELECT id, resource_type, sequence_order" in str(statement) and "allocation_requirements" in str(statement):
            if self.existing_requirements:
                # Return existing requirements as tuples (id, resource_type, sequence_order)
                result.fetchall.return_value = self.existing_requirements
            else:
                result.fetchall.return_value = []
        else:
            result.fetchone.return_value = None
            result.fetchall.return_value = []

        return result


class FakeSessionFactory:
    """Fake session factory for testing."""

    def __init__(self, session: FakeAsyncSession):
        self.session = session

    def __call__(self):
        return self.session


class TestIdempotency:
    """Tests for idempotency behavior."""

    @pytest.fixture
    def sample_request(self) -> AllocationRequest:
        """Create a sample allocation request."""
        correlation_id = uuid4()
        tenant_id = uuid4()
        
        metadata = AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=tenant_id,
            message_type="RESOURCE_ALLOCATION_REQUEST",
        )
        
        return AllocationRequest(
            metadata=metadata,
            human_requirements=HumanResourceRequirement(
                resource_type=ResourceType.HUMAN,
                requester_id=uuid4(),
                task_deadline=datetime(2026, 6, 1, tzinfo=timezone.utc),
                estimated_effort_hours=Decimal("10"),
                process_stage="resource_allocation",
            ),
            budget_requirements=None,
        )

    @pytest.fixture
    def sample_recommendation(self, sample_request: AllocationRequest) -> AllocationRecommendation:
        """Create a sample allocation recommendation."""
        metadata = AgentMessageMetadata(
            correlation_id=sample_request.metadata.correlation_id,
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=sample_request.metadata.tenant_id,
            message_type="RESOURCE_ALLOCATION_RESPONSE",
        )
        
        return AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.PENDING_HUMAN_APPROVAL,
            requires_human_approval=True,
            manual_intervention_required=False,
            explanation="Test recommendation",
            confidence=Decimal("0.85"),
            human_requirement_result=RequirementResult(
                resource_type=ResourceType.HUMAN,
                eligible_candidates=[],
                excluded_resources=[],
            ),
            budget_requirement_result=None,
            resource_gaps=[],
            alternatives=[],
            limitations=[],
        )

    def test_first_persist_creates_request(
        self,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test that first persist creates a new request."""
        fake_session = FakeAsyncSession(existing_request=None)
        session_factory = FakeSessionFactory(fake_session)
        repository = RecommendationWriteRepository(session_factory)
        
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        asyncio.run(repository.persist_allocation_result(
            sample_request,
            sample_recommendation,
            evaluation_timestamp,
        ))
        
        # Check that INSERT request was called
        assert fake_session.committed
        assert not fake_session.rolled_back

    def test_duplicate_request_with_existing_recommendation_raises_conflict(
        self,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test that duplicate request with existing recommendation raises conflict."""
        existing_request_id = uuid4()
        existing_recommendation_id = uuid4()

        fake_session = FakeAsyncSession(
            existing_request=(existing_request_id, sample_request.metadata.tenant_id, sample_request.metadata.correlation_id),
            existing_recommendation=(existing_recommendation_id,),
        )
        session_factory = FakeSessionFactory(fake_session)
        repository = RecommendationWriteRepository(session_factory)

        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        with pytest.raises(PersistenceConflictError, match="Recommendation already exists"):
            asyncio.run(repository.persist_allocation_result(
                sample_request,
                sample_recommendation,
                evaluation_timestamp,
            ))

    def test_duplicate_request_with_allow_versioning_succeeds(
        self,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test that duplicate request with allow_versioning=True allows versioning."""
        existing_request_id = uuid4()
        existing_recommendation_id = uuid4()
        existing_human_req_id = uuid4()

        fake_session = FakeAsyncSession(
            existing_request=(existing_request_id, sample_request.metadata.tenant_id, sample_request.metadata.correlation_id),
            existing_recommendation=(existing_recommendation_id,),
            existing_requirements=[(existing_human_req_id, "HUMAN", 1)],  # Existing HUMAN requirement
        )
        session_factory = FakeSessionFactory(fake_session)
        repository = RecommendationWriteRepository(session_factory)

        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        # Should succeed with allow_versioning=True
        asyncio.run(repository.persist_allocation_result(
            sample_request,
            sample_recommendation,
            evaluation_timestamp,
            allow_versioning=True,
        ))

        assert fake_session.committed
        assert not fake_session.rolled_back

    def test_duplicate_request_without_recommendation_reuses_request(
        self,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test that duplicate request without recommendation reuses existing request."""
        existing_request_id = uuid4()
        
        fake_session = FakeAsyncSession(
            existing_request=(existing_request_id, sample_request.metadata.tenant_id, sample_request.metadata.correlation_id),
            existing_recommendation=None,
        )
        session_factory = FakeSessionFactory(fake_session)
        repository = RecommendationWriteRepository(session_factory)
        
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        asyncio.run(repository.persist_allocation_result(
            sample_request,
            sample_recommendation,
            evaluation_timestamp,
        ))
        
        # Should commit successfully (reusing existing request)
        assert fake_session.committed
        assert not fake_session.rolled_back

    def test_idempotency_key_deterministic(
        self,
        sample_request: AllocationRequest,
    ) -> None:
        """Test that idempotency key is deterministic for same request."""
        from app.agents.agent3_resources.repositories.write_mappers import generate_idempotency_key
        
        key1 = generate_idempotency_key(sample_request)
        key2 = generate_idempotency_key(sample_request)
        
        assert key1 == key2

    def test_idempotency_key_includes_correlation_and_tenant(
        self,
        sample_request: AllocationRequest,
    ) -> None:
        """Test that idempotency key includes correlation_id and tenant_id."""
        from app.agents.agent3_resources.repositories.write_mappers import generate_idempotency_key
        
        key = generate_idempotency_key(sample_request)
        
        assert str(sample_request.metadata.correlation_id) in key
        assert str(sample_request.metadata.tenant_id) in key

    def test_different_correlation_id_different_key(
        self,
        sample_request: AllocationRequest,
    ) -> None:
        """Test that different correlation_id produces different key."""
        from app.agents.agent3_resources.repositories.write_mappers import generate_idempotency_key
        
        key1 = generate_idempotency_key(sample_request)
        
        # Change correlation_id
        sample_request.metadata.correlation_id = uuid4()
        key2 = generate_idempotency_key(sample_request)
        
        assert key1 != key2

    def test_different_tenant_id_different_key(
        self,
        sample_request: AllocationRequest,
    ) -> None:
        """Test that different tenant_id produces different key."""
        from app.agents.agent3_resources.repositories.write_mappers import generate_idempotency_key
        
        key1 = generate_idempotency_key(sample_request)
        
        # Change tenant_id
        sample_request.metadata.tenant_id = uuid4()
        key2 = generate_idempotency_key(sample_request)
        
        assert key1 != key2


import asyncio
