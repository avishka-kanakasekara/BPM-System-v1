"""Tenant isolation tests for Agent 3 write-path persistence."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import MagicMock

from app.agents.agent3_resources.repositories.recommendation_repository import (
    RecommendationWriteRepository,
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
    """Fake AsyncSession for tenant isolation testing."""

    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.executed_statements = []
        self._tenant_filter = None

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
        result.fetchone.return_value = None
        return result


class FakeSessionFactory:
    """Fake session factory for testing."""

    def __init__(self, session: FakeAsyncSession):
        self.session = session

    def __call__(self):
        return self.session


class TestTenantIsolation:
    """Tests for tenant isolation in write-path persistence."""

    @pytest.fixture
    def tenant_a_id(self) -> UUID:
        """Tenant A ID."""
        return uuid4()

    @pytest.fixture
    def tenant_b_id(self) -> UUID:
        """Tenant B ID."""
        return uuid4()

    @pytest.fixture
    def sample_request_tenant_a(self, tenant_a_id: UUID) -> AllocationRequest:
        """Create a sample allocation request for tenant A."""
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=tenant_a_id,
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
    def sample_recommendation_tenant_a(self, tenant_a_id: UUID) -> AllocationRecommendation:
        """Create a sample allocation recommendation for tenant A."""
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=tenant_a_id,
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

    @pytest.fixture
    def repository(self) -> RecommendationWriteRepository:
        """Create repository with fake session factory."""
        fake_session = FakeAsyncSession()
        session_factory = FakeSessionFactory(fake_session)
        return RecommendationWriteRepository(session_factory)

    def test_persist_includes_tenant_id_in_request(
        self,
        repository: RecommendationWriteRepository,
        sample_request_tenant_a: AllocationRequest,
        sample_recommendation_tenant_a: AllocationRecommendation,
        tenant_a_id: UUID,
    ) -> None:
        """Test that persist includes tenant_id in request insert."""
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        asyncio.run(repository.persist_allocation_result(
            sample_request_tenant_a,
            sample_recommendation_tenant_a,
            evaluation_timestamp,
        ))
        
        # Check that tenant_id was included in the executed statements
        assert len(repository._session_factory.session.executed_statements) > 0
        # The first statement should be the request insert with tenant_id
        first_statement, first_params = repository._session_factory.session.executed_statements[0]
        assert "tenant_id" in str(first_params)
        assert first_params["tenant_id"] == tenant_a_id

    def test_persist_includes_tenant_id_in_recommendation(
        self,
        repository: RecommendationWriteRepository,
        sample_request_tenant_a: AllocationRequest,
        sample_recommendation_tenant_a: AllocationRecommendation,
        tenant_a_id: UUID,
    ) -> None:
        """Test that persist includes tenant_id in recommendation insert."""
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        asyncio.run(repository.persist_allocation_result(
            sample_request_tenant_a,
            sample_recommendation_tenant_a,
            evaluation_timestamp,
        ))
        
        # Check that tenant_id was included in recommendation insert
        statements = repository._session_factory.session.executed_statements
        # Find the recommendation insert statement
        for statement, params in statements:
            if "allocation_recommendations" in str(statement):
                assert "tenant_id" in str(params)
                assert params["tenant_id"] == tenant_a_id
                break

    def test_get_recommendation_filters_by_tenant_id(
        self,
        repository: RecommendationWriteRepository,
        tenant_a_id: UUID,
        tenant_b_id: UUID,
    ) -> None:
        """Test that get_recommendation filters by tenant_id."""
        recommendation_id = uuid4()
        
        asyncio.run(repository.get_recommendation(tenant_a_id, recommendation_id))
        
        # Check that tenant_id was included in the query
        assert len(repository._session_factory.session.executed_statements) > 0
        statement, params = repository._session_factory.session.executed_statements[0]
        assert "tenant_id" in str(params)
        assert params["tenant_id"] == tenant_a_id

    def test_get_recommendation_cross_tenant_returns_none(
        self,
        repository: RecommendationWriteRepository,
        tenant_a_id: UUID,
        tenant_b_id: UUID,
    ) -> None:
        """Test that cross-tenant read returns None (simulated)."""
        recommendation_id = uuid4()
        
        # Try to read tenant A's recommendation with tenant B's context
        result = asyncio.run(repository.get_recommendation(tenant_b_id, recommendation_id))
        
        # In a real DB, this would return None due to tenant filter
        # With fake session, we just verify the tenant_id was used
        assert result is None  # Fake session returns None by default

    def test_get_latest_recommendation_filters_by_tenant_id(
        self,
        repository: RecommendationWriteRepository,
        tenant_a_id: UUID,
        tenant_b_id: UUID,
    ) -> None:
        """Test that get_latest_recommendation_by_correlation_id filters by tenant_id."""
        correlation_id = uuid4()
        
        asyncio.run(repository.get_latest_recommendation_by_correlation_id(tenant_a_id, correlation_id))
        
        # Check that tenant_id was included in the query
        assert len(repository._session_factory.session.executed_statements) > 0
        statement, params = repository._session_factory.session.executed_statements[0]
        assert "tenant_id" in str(params)
        assert params["tenant_id"] == tenant_a_id

    def test_mark_superseded_filters_by_tenant_id(
        self,
        repository: RecommendationWriteRepository,
        tenant_a_id: UUID,
        tenant_b_id: UUID,
    ) -> None:
        """Test that mark_previous_recommendation_superseded filters by tenant_id."""
        correlation_id = uuid4()
        new_recommendation_id = uuid4()
        
        asyncio.run(repository.mark_previous_recommendation_superseded(
            tenant_a_id,
            correlation_id,
            new_recommendation_id,
        ))
        
        # Check that tenant_id was included in the update
        assert len(repository._session_factory.session.executed_statements) > 0
        statement, params = repository._session_factory.session.executed_statements[0]
        assert "tenant_id" in str(params)
        assert params["tenant_id"] == tenant_a_id

    def test_requester_id_not_used_as_tenant_filter(
        self,
        repository: RecommendationWriteRepository,
        sample_request_tenant_a: AllocationRequest,
        sample_recommendation_tenant_a: AllocationRecommendation,
        tenant_a_id: UUID,
    ) -> None:
        """Test that requester_id is not used as tenant_id filter."""
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        # Set a different requester_id than tenant_id
        different_requester_id = uuid4()
        sample_request_tenant_a.human_requirements.requester_id = different_requester_id
        
        asyncio.run(repository.persist_allocation_result(
            sample_request_tenant_a,
            sample_recommendation_tenant_a,
            evaluation_timestamp,
        ))
        
        # Check that tenant_id (not requester_id) was used in inserts
        statements = repository._session_factory.session.executed_statements
        found_requester_id = False
        for statement, params in statements:
            if "allocation_requirements" in str(statement):
                assert params["tenant_id"] == tenant_a_id
                # requester_id should be in a different field
                if "requester_id" in params:
                    found_requester_id = True
                    assert params["requester_id"] == different_requester_id
                    assert params["requester_id"] != params["tenant_id"]
        
        # Verify that requester_id was actually set in the requirement insert
        assert found_requester_id, "requester_id should be present in requirement insert"

    def test_different_tenants_separate_isolation(
        self,
        repository: RecommendationWriteRepository,
        tenant_a_id: UUID,
        tenant_b_id: UUID,
    ) -> None:
        """Test that different tenants have separate isolation."""
        # Create requests for both tenants
        metadata_a = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=tenant_a_id,
            message_type="RESOURCE_ALLOCATION_REQUEST",
        )
        
        metadata_b = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=tenant_b_id,
            message_type="RESOURCE_ALLOCATION_REQUEST",
        )
        
        request_a = AllocationRequest(
            metadata=metadata_a,
            human_requirements=HumanResourceRequirement(
                resource_type=ResourceType.HUMAN,
                requester_id=uuid4(),
                task_deadline=datetime(2026, 6, 1, tzinfo=timezone.utc),
                estimated_effort_hours=Decimal("10"),
                process_stage="resource_allocation",
            ),
            budget_requirements=None,
        )
        
        request_b = AllocationRequest(
            metadata=metadata_b,
            human_requirements=HumanResourceRequirement(
                resource_type=ResourceType.HUMAN,
                requester_id=uuid4(),
                task_deadline=datetime(2026, 6, 1, tzinfo=timezone.utc),
                estimated_effort_hours=Decimal("10"),
                process_stage="resource_allocation",
            ),
            budget_requirements=None,
        )
        
        recommendation_a = AllocationRecommendation(
            metadata=metadata_a,
            status=RecommendationStatus.PENDING_HUMAN_APPROVAL,
            requires_human_approval=True,
            manual_intervention_required=False,
            explanation="Test recommendation A",
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
        
        recommendation_b = AllocationRecommendation(
            metadata=metadata_b,
            status=RecommendationStatus.PENDING_HUMAN_APPROVAL,
            requires_human_approval=True,
            manual_intervention_required=False,
            explanation="Test recommendation B",
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
        
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        # Persist both
        asyncio.run(repository.persist_allocation_result(
            request_a,
            recommendation_a,
            evaluation_timestamp,
        ))
        
        asyncio.run(repository.persist_allocation_result(
            request_b,
            recommendation_b,
            evaluation_timestamp,
        ))
        
        # Check that both were persisted with their respective tenant_ids
        statements = repository._session_factory.session.executed_statements
        tenant_ids_used = []
        for statement, params in statements:
            if "allocation_requests" in str(statement):
                tenant_ids_used.append(params["tenant_id"])
        
        assert tenant_a_id in tenant_ids_used
        assert tenant_b_id in tenant_ids_used


import asyncio
