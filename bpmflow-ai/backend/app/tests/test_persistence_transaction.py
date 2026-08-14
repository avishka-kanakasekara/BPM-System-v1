"""Transaction and rollback tests for Agent 3 write-path persistence."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock

from app.agents.agent3_resources.repositories.recommendation_repository import (
    RecommendationWriteRepository,
)
from app.agents.agent3_resources.repositories.persistence_exceptions import (
    PersistenceTransactionError,
)
from app.agents.agent3_resources.schemas import (
    AllocationRequest,
    AllocationRecommendation,
    HumanResourceRequirement,
    RequirementResult,
    RankedCandidate,
    AgentMessageMetadata,
    RecommendationStatus,
    ResourceType,
)


class FakeAsyncSession:
    """Fake AsyncSession for transaction testing."""

    def __init__(self, fail_on=None):
        self.committed = False
        self.rolled_back = False
        self.fail_on = fail_on
        self.executed_statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def commit(self):
        if self.fail_on == "commit":
            raise Exception("Commit failed")
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def execute(self, statement, params=None):
        if self.fail_on == "execute":
            raise Exception("Execute failed")
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


class TestTransactionRollback:
    """Tests for transaction rollback behavior."""

    @pytest.fixture
    def sample_request(self) -> AllocationRequest:
        """Create a sample allocation request."""
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
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
    def sample_recommendation(self) -> AllocationRecommendation:
        """Create a sample allocation recommendation."""
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
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

    def test_rollback_on_execute_failure(
        self,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test that transaction rolls back when execute fails."""
        fake_session = FakeAsyncSession(fail_on="execute")
        session_factory = FakeSessionFactory(fake_session)
        repository = RecommendationWriteRepository(session_factory)
        
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        with pytest.raises(PersistenceTransactionError):
            asyncio.run(repository.persist_allocation_result(
                sample_request,
                sample_recommendation,
                evaluation_timestamp,
            ))
        
        assert fake_session.rolled_back
        assert not fake_session.committed

    def test_rollback_on_commit_failure(
        self,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test that transaction rolls back when commit fails."""
        fake_session = FakeAsyncSession(fail_on="commit")
        session_factory = FakeSessionFactory(fake_session)
        repository = RecommendationWriteRepository(session_factory)
        
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        with pytest.raises(PersistenceTransactionError):
            asyncio.run(repository.persist_allocation_result(
                sample_request,
                sample_recommendation,
                evaluation_timestamp,
            ))
        
        assert fake_session.rolled_back
        assert not fake_session.committed

    def test_commit_on_success(
        self,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test that transaction commits on success."""
        fake_session = FakeAsyncSession()
        session_factory = FakeSessionFactory(fake_session)
        repository = RecommendationWriteRepository(session_factory)
        
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        asyncio.run(repository.persist_allocation_result(
            sample_request,
            sample_recommendation,
            evaluation_timestamp,
        ))
        
        assert fake_session.committed
        assert not fake_session.rolled_back

    def test_rollback_on_child_insert_failure(
        self,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test that transaction rolls back when child insert fails."""
        fake_session = FakeAsyncSession()
        
        # Make second execute call fail (child insert)
        execute_count = [0]
        original_execute = fake_session.execute
        
        async def failing_execute(statement, params=None):
            execute_count[0] += 1
            if execute_count[0] > 1:  # Fail on second call
                raise Exception("Child insert failed")
            return await original_execute(statement, params)
        
        fake_session.execute = failing_execute
        session_factory = FakeSessionFactory(fake_session)
        repository = RecommendationWriteRepository(session_factory)
        
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        with pytest.raises(PersistenceTransactionError):
            asyncio.run(repository.persist_allocation_result(
                sample_request,
                sample_recommendation,
                evaluation_timestamp,
            ))
        
        assert fake_session.rolled_back
        assert not fake_session.committed


import asyncio
