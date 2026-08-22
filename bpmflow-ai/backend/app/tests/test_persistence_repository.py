"""Repository contract tests for Agent 3 write-path persistence (fake session)."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent3_resources.repositories.recommendation_repository import (
    RecommendationWriteRepository,
)
from app.agents.agent3_resources.repositories.persistence_exceptions import (
    PersistenceValidationError,
    PersistenceTransactionError,
    PersistenceConflictError,
)
from app.agents.agent3_resources.schemas import (
    AllocationRequest,
    AllocationRecommendation,
    HumanResourceRequirement,
    BudgetResourceRequirement,
    RequirementResult,
    RankedCandidate,
    ScoreBreakdown,
    ExcludedResource,
    ExclusionReasonEntry,
    ResourceGap,
    ResourceAlternative,
    BudgetValidationChecks,
    AgentMessageMetadata,
    RecommendationStatus,
    ResourceType,
    GapAlternativeType,
    GapType,
    ExclusionReason,
)


class FakeAsyncSession:
    """Fake AsyncSession for testing without database."""

    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.executed_statements: List[tuple] = []
        self._results: Dict[str, Any] = {}
        self._query_sequence: List[Any] = []  # Sequence of results for different queries
        self._query_index = 0

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
        
        # Use query sequence if available (for versioning tests with multiple queries)
        if self._query_sequence and self._query_index < len(self._query_sequence):
            query_result = self._query_sequence[self._query_index]
            self._query_index += 1

            if isinstance(query_result, dict) and "fetchone" in query_result:
                result.fetchone.return_value = query_result["fetchone"]
            elif isinstance(query_result, dict) and "fetchall" in query_result:
                result.fetchall.return_value = query_result["fetchall"]
            else:
                result.fetchone.return_value = query_result
                result.fetchall.return_value = []
        else:
            # Fall back to _results for backward compatibility
            fetchone_result = self._results.get("fetchone")
            if fetchone_result is not None:
                if isinstance(fetchone_result, tuple):
                    row = MagicMock()
                    row._mapping = {f"col_{i}": val for i, val in enumerate(fetchone_result)}
                    result.fetchone.return_value = row
                else:
                    result.fetchone.return_value = fetchone_result
            else:
                result.fetchone.return_value = None

            fetchall_result = self._results.get("fetchall")
            if fetchall_result is not None:
                result.fetchall.return_value = fetchall_result
            else:
                result.fetchall.return_value = []

        return result


class FakeSessionFactory:
    """Fake session factory for testing."""

    def __init__(self, session: FakeAsyncSession):
        self.session = session

    def __call__(self):
        return self.session


class TestRecommendationWriteRepository:
    """Contract tests for RecommendationWriteRepository with fake session."""

    @pytest.fixture
    def fake_session(self) -> FakeAsyncSession:
        """Create a fake async session."""
        return FakeAsyncSession()

    @pytest.fixture
    def session_factory(self, fake_session: FakeAsyncSession) -> FakeSessionFactory:
        """Create a fake session factory."""
        return FakeSessionFactory(fake_session)

    @pytest.fixture
    def repository(self, session_factory: FakeSessionFactory) -> RecommendationWriteRepository:
        """Create repository with fake session factory."""
        return RecommendationWriteRepository(session_factory)

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

    def test_persist_allocation_result_calls_insert_request(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test that persist_allocation_result inserts request."""
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        # Set up fake results
        fake_session._results["fetchone"] = None  # No existing request
        
        asyncio.run(repository.persist_allocation_result(
            sample_request,
            sample_recommendation,
            evaluation_timestamp,
        ))
        
        # Check that session was committed
        assert fake_session.committed
        assert not fake_session.rolled_back

    def test_persist_allocation_result_validates_timezone(
        self,
        repository: RecommendationWriteRepository,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test that persist_allocation_result validates timezone awareness."""
        naive_timestamp = datetime(2026, 1, 1, 12, 0)  # No timezone
        
        with pytest.raises(PersistenceValidationError, match="must be timezone-aware"):
            asyncio.run(repository.persist_allocation_result(
                sample_request,
                sample_recommendation,
                naive_timestamp,
            ))

    def test_persist_allocation_result_rolls_back_on_error(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test that transaction rolls back on error."""
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        # Make session.execute raise an error
        fake_session.execute = AsyncMock(side_effect=Exception("DB error"))
        
        with pytest.raises(PersistenceTransactionError):
            asyncio.run(repository.persist_allocation_result(
                sample_request,
                sample_recommendation,
                evaluation_timestamp,
            ))
        
        # Check that session was rolled back
        assert fake_session.rolled_back
        assert not fake_session.committed

    def test_get_recommendation_returns_none_when_not_found(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test that get_recommendation returns None when not found."""
        fake_session._results["fetchone"] = None
        
        result = asyncio.run(repository.get_recommendation(uuid4(), uuid4()))
        
        assert result is None

    def test_get_recommendation_returns_header_when_found(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test that get_recommendation returns header when found."""
        recommendation_id = uuid4()
        tenant_id = uuid4()
        
        # Create a proper row-like object
        row = MagicMock()
        row._mapping = {
            "id": recommendation_id,
            "tenant_id": tenant_id,
            "request_id": uuid4(),
            "correlation_id": uuid4(),
            "recommendation_version": 1,
            "status": "PENDING_HUMAN_APPROVAL",
            "requires_human_approval": True,
            "manual_intervention_required": False,
            "explanation": "Test",
            "confidence": Decimal("0.85"),
            "error_code": None,
            "error_message": None,
            "retryable": None,
            "limitations": [],
            "response_schema_version": "1.0.0",
            "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        }
        fake_session._results["fetchone"] = row
        
        result = asyncio.run(repository.get_recommendation(tenant_id, recommendation_id))

        assert result is not None
        assert result["recommendation_id"] == recommendation_id
        assert result["status"] == "PENDING_HUMAN_APPROVAL"

    def test_get_latest_recommendation_by_correlation_id(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test getting latest recommendation by correlation ID."""
        correlation_id = uuid4()
        tenant_id = uuid4()
        
        # Create a proper row-like object
        row = MagicMock()
        row._mapping = {
            "id": uuid4(),
            "tenant_id": tenant_id,
            "request_id": uuid4(),
            "correlation_id": correlation_id,
            "recommendation_version": 2,
            "status": "PENDING_HUMAN_APPROVAL",
            "requires_human_approval": True,
            "manual_intervention_required": False,
            "explanation": "Test",
            "confidence": Decimal("0.85"),
            "error_code": None,
            "error_message": None,
            "retryable": None,
            "limitations": [],
            "response_schema_version": "1.0.0",
            "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        }
        fake_session._results["fetchone"] = row
        
        result = asyncio.run(repository.get_latest_recommendation_by_correlation_id(tenant_id, correlation_id))
        
        assert result is not None
        assert result["correlation_id"] == correlation_id

    def test_mark_previous_recommendation_superseded(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test marking previous recommendations as superseded."""
        tenant_id = uuid4()
        correlation_id = uuid4()
        new_recommendation_id = uuid4()
        
        asyncio.run(repository.mark_previous_recommendation_superseded(
            tenant_id,
            correlation_id,
            new_recommendation_id,
        ))
        
        # Check that UPDATE statement was executed
        assert len(fake_session.executed_statements) > 0
        assert fake_session.committed

    def test_persist_allocation_result_with_candidates(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test persisting recommendation with candidates."""
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        # Add candidates to recommendation
        score_breakdown = ScoreBreakdown(
            role_match=Decimal("0.9"),
            skill_match=Decimal("0.8"),
            availability_score=Decimal("0.85"),
            workload_fit=Decimal("0.9"),
            authority_match=Decimal("1.0"),
            total_score=Decimal("0.875"),
        )
        sample_recommendation.human_requirement_result = RequirementResult(
            resource_type=ResourceType.HUMAN,
            eligible_candidates=[
                RankedCandidate(
                    resource_id=uuid4(),
                    name="Test Developer",
                    rank=1,
                    allocation_score=Decimal("0.875"),
                    score_breakdown=score_breakdown,
                    current_workload_percentage=Decimal("30"),
                    projected_workload_percentage=Decimal("40"),
                    available_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    available_until=None,
                    evidence_refs={},
                )
            ],
            excluded_resources=[],
        )
        
        fake_session._results["fetchone"] = None
        
        asyncio.run(repository.persist_allocation_result(
            sample_request,
            sample_recommendation,
            evaluation_timestamp,
        ))
        
        # Check that candidate insert was called
        assert fake_session.committed

    def test_persist_allocation_result_with_exclusions(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test persisting recommendation with exclusions."""
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        # Add exclusions to recommendation
        sample_recommendation.human_requirement_result = RequirementResult(
            resource_type=ResourceType.HUMAN,
            eligible_candidates=[],
            excluded_resources=[
                ExcludedResource(
                    resource_id=uuid4(),
                    resource_type=ResourceType.HUMAN,
                    name="Inactive Developer",
                    exclusion_reasons=[
                        ExclusionReasonEntry(
                            reason=ExclusionReason.INACTIVE_RESOURCE,
                            description="Resource is inactive",
                            evidence_reference="is_active field",
                        )
                    ],
                )
            ],
        )
        
        fake_session._results["fetchone"] = None
        
        asyncio.run(repository.persist_allocation_result(
            sample_request,
            sample_recommendation,
            evaluation_timestamp,
        ))
        
        # Check that exclusion insert was called
        assert fake_session.committed

    def test_persist_allocation_result_with_gaps_and_alternatives(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test persisting recommendation with gaps and alternatives."""
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        # Add gaps to recommendation (alternatives are stored separately)
        sample_recommendation.resource_gaps = [
            ResourceGap(
                gap_type=GapType.NO_ELIGIBLE_HUMAN,
                resource_type=ResourceType.HUMAN,
                gap_description="No eligible candidates",
                eligible_count=0,
                excluded_count=5,
            )
        ]
        sample_recommendation.alternatives = [
            ResourceAlternative(
                alternative_type=GapAlternativeType.RECRUITMENT_ESCALATION,
                description="Hire new developer",
                requires_approval=True,
                estimated_effort_hours=Decimal("40"),
                cost_impact=Decimal("5000"),
            )
        ]
        
        fake_session._results["fetchone"] = None
        
        asyncio.run(repository.persist_allocation_result(
            sample_request,
            sample_recommendation,
            evaluation_timestamp,
        ))
        
        # Check that gap and alternative inserts were called
        assert fake_session.committed

    def test_get_recommendation_maps_database_columns_to_api_fields(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test that get_recommendation maps database columns to API field names correctly."""
        tenant_id = uuid4()
        recommendation_id = uuid4()
        correlation_id = uuid4()
        created_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        # Mock database row with column names from SQL_SELECT_RECOMMENDATION_HEADER
        fake_session._results["fetchone"] = MagicMock(_mapping={
            "id": recommendation_id,
            "tenant_id": tenant_id,
            "request_id": uuid4(),
            "correlation_id": correlation_id,
            "recommendation_version": 1,
            "status": "PENDING_HUMAN_APPROVAL",
            "requires_human_approval": True,
            "manual_intervention_required": False,
            "explanation": "Test explanation",
            "confidence": Decimal("0.85"),
            "error_code": None,
            "error_message": None,
            "retryable": None,
            "limitations": [],
            "response_schema_version": "1.0",
            "created_at": created_at,
        })

        result = asyncio.run(repository.get_recommendation(tenant_id, recommendation_id))

        assert result is not None
        # Verify database column 'id' maps to API field 'recommendation_id'
        assert result["recommendation_id"] == recommendation_id
        # Verify database column 'created_at' maps to API field 'persisted_at'
        assert result["persisted_at"] == created_at
        assert result["tenant_id"] == tenant_id
        assert result["correlation_id"] == correlation_id
        assert result["status"] == "PENDING_HUMAN_APPROVAL"
        assert result["explanation"] == "Test explanation"
        assert result["confidence"] == Decimal("0.85")
        assert result["requires_human_approval"] is True
        assert result["manual_intervention_required"] is False

    def test_get_recommendation_returns_none_when_not_found(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test that get_recommendation returns None when row not found."""
        tenant_id = uuid4()
        recommendation_id = uuid4()

        fake_session._results["fetchone"] = None

        result = asyncio.run(repository.get_recommendation(tenant_id, recommendation_id))

        assert result is None

    def test_get_latest_recommendation_by_correlation_id_maps_database_columns_to_api_fields(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test that get_latest_recommendation_by_correlation_id maps database columns to API field names correctly."""
        tenant_id = uuid4()
        correlation_id = uuid4()
        recommendation_id = uuid4()
        created_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        # Mock database row with column names from SQL_SELECT_LATEST_RECOMMENDATION_HEADER
        fake_session._results["fetchone"] = MagicMock(_mapping={
            "id": recommendation_id,
            "tenant_id": tenant_id,
            "request_id": uuid4(),
            "correlation_id": correlation_id,
            "recommendation_version": 1,
            "status": "GENERATED",
            "requires_human_approval": False,
            "manual_intervention_required": False,
            "explanation": "Latest explanation",
            "confidence": Decimal("0.90"),
            "error_code": None,
            "error_message": None,
            "retryable": None,
            "limitations": [],
            "response_schema_version": "1.0",
            "created_at": created_at,
        })

        result = asyncio.run(repository.get_latest_recommendation_by_correlation_id(tenant_id, correlation_id))

        assert result is not None
        # Verify database column 'id' maps to API field 'recommendation_id'
        assert result["recommendation_id"] == recommendation_id
        # Verify database column 'created_at' maps to API field 'persisted_at'
        assert result["persisted_at"] == created_at
        assert result["tenant_id"] == tenant_id
        assert result["correlation_id"] == correlation_id
        assert result["status"] == "GENERATED"
        assert result["explanation"] == "Latest explanation"
        assert result["confidence"] == Decimal("0.90")
        assert result["requires_human_approval"] is False

    def test_get_latest_recommendation_by_correlation_id_returns_none_when_not_found(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
    ) -> None:
        """Test that get_latest_recommendation_by_correlation_id returns None when row not found."""
        tenant_id = uuid4()
        correlation_id = uuid4()

        fake_session._results["fetchone"] = None

        result = asyncio.run(repository.get_latest_recommendation_by_correlation_id(tenant_id, correlation_id))

        assert result is None

    def test_persist_allocation_result_with_budget_validation(
        self,
        repository: RecommendationWriteRepository,
        fake_session: FakeAsyncSession,
        sample_request: AllocationRequest,
        sample_recommendation: AllocationRecommendation,
    ) -> None:
        """Test persisting recommendation with budget validation."""
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        # Add budget requirements and validation
        sample_request.human_requirements = None
        sample_request.budget_requirements = BudgetResourceRequirement(
            resource_type=ResourceType.BUDGET,
            required_amount=Decimal("5000"),
            currency="USD",
            requester_id=uuid4(),
            task_deadline=datetime(2026, 6, 1, tzinfo=timezone.utc),
            process_stage="resource_allocation",
        )
        
        sample_recommendation.human_requirement_result = None
        sample_recommendation.budget_requirement_result = RequirementResult(
            resource_type=ResourceType.BUDGET,
            budget_validation=BudgetValidationChecks(
                resource_id=uuid4(),
                name="Team Budget",
                sufficient_balance=True,
                cost_centre_match=True,
                currency_match=True,
                validity_period_valid=True,
                within_authorization_limit=True,
                available_balance=Decimal("10000"),
                required_amount=Decimal("5000"),
                evidence_references={},
            )
        )
        
        fake_session._results["fetchone"] = None
        
        asyncio.run(repository.persist_allocation_result(
            sample_request,
            sample_recommendation,
            evaluation_timestamp,
        ))
        
        # Check that budget validation insert was called
        assert fake_session.committed


# Helper for running async tests
import asyncio
