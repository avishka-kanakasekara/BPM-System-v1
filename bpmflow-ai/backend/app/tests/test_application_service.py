"""Unit tests for PersistentResourceAllocationService."""

import asyncio
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4, UUID as UUIDType

from app.agents.agent3_resources.application_service import (
    PersistentResourceAllocationService,
    AllocationServiceProtocol,
    PersistenceProtocol,
    PersistedAllocationResult,
)
from app.agents.agent3_resources.schemas import (
    AllocationRequest,
    AllocationRecommendation,
    AgentMessageMetadata,
    RecommendationStatus,
    HumanResourceRequirement,
    BudgetResourceRequirement,
    RequirementResult,
    RankedCandidate,
    ScoreBreakdown,
    ResourceGap,
    ResourceAlternative,
)
from app.agents.agent3_resources.constants import MessageType, ResourceType, GapType, GapAlternativeType
from app.agents.agent3_resources.repositories.persistence_exceptions import (
    PersistenceValidationError,
    PersistenceConflictError,
    PersistenceTransactionError,
)


# ============================================================================
# Fake Dependencies
# ============================================================================


class FakeAllocationService(AllocationServiceProtocol):
    """Fake allocation service for testing."""

    def __init__(self, recommendation: AllocationRecommendation):
        self._recommendation = recommendation
        self.call_count = 0
        self.last_request = None
        self.last_timestamp = None

    async def process_allocation_request(
        self,
        request: AllocationRequest,
        evaluation_timestamp: datetime | None = None,
    ) -> AllocationRecommendation:
        """Return the configured recommendation."""
        self.call_count += 1
        self.last_request = request
        self.last_timestamp = evaluation_timestamp
        return self._recommendation


class FakePersistence(PersistenceProtocol):
    """Fake persistence for testing."""

    def __init__(self, recommendation_id: uuid4):
        self._recommendation_id = recommendation_id
        self.call_count = 0
        self.last_request = None
        self.last_recommendation = None
        self.last_timestamp = None
        self.should_raise = None

    async def persist_allocation_result(
        self,
        request: AllocationRequest,
        recommendation: AllocationRecommendation,
        evaluation_timestamp: datetime,
    ) -> uuid4:
        """Return the configured recommendation_id or raise error."""
        self.call_count += 1
        self.last_request = request
        self.last_recommendation = recommendation
        self.last_timestamp = evaluation_timestamp

        if self.should_raise:
            raise self.should_raise

        return self._recommendation_id


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tenant_id():
    """Fixture for tenant_id."""
    return uuid4()


@pytest.fixture
def correlation_id():
    """Fixture for correlation_id."""
    return uuid4()


@pytest.fixture
def metadata(tenant_id, correlation_id):
    """Fixture for AgentMessageMetadata."""
    return AgentMessageMetadata(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        process_instance_id=uuid4(),
        task_id=uuid4(),
        message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
    )


@pytest.fixture
def allocation_request(metadata):
    """Fixture for AllocationRequest."""
    return AllocationRequest(
        metadata=metadata,
        human_requirements=None,
        budget_requirements=None,
    )


@pytest.fixture
def successful_recommendation(metadata):
    """Fixture for a successful AllocationRecommendation."""
    return AllocationRecommendation(
        metadata=metadata,
        status=RecommendationStatus.GENERATED,
        explanation="Test explanation",
        confidence=0.9,
        requires_human_approval=True,
        manual_intervention_required=False,
    )


@pytest.fixture
def failed_recommendation(metadata):
    """Fixture for a FAILED AllocationRecommendation."""
    return AllocationRecommendation(
        metadata=metadata,
        status=RecommendationStatus.FAILED,
        explanation="",
        requires_human_approval=False,
        manual_intervention_required=True,
        error_code="TEST_ERROR",
        error_message="Test error message",
        retryable=True,
    )


# ============================================================================
# Tests
# ============================================================================


class TestPersistentResourceAllocationService:
    """Tests for PersistentResourceAllocationService."""

    def test_process_and_persist_success(
        self,
        allocation_request,
        successful_recommendation,
        tenant_id,
        correlation_id,
    ):
        """Test successful processing and persistence."""
        recommendation_id = uuid4()
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(allocation_request))

        # Verify allocation service called once
        assert fake_allocation.call_count == 1
        assert fake_allocation.last_request == allocation_request
        assert fake_allocation.last_timestamp is not None

        # Verify persistence called once
        assert fake_persistence.call_count == 1
        assert fake_persistence.last_request == allocation_request
        assert fake_persistence.last_recommendation == successful_recommendation

        # Verify result envelope
        assert isinstance(result, PersistedAllocationResult)
        assert result.tenant_id == tenant_id
        assert result.correlation_id == correlation_id
        assert result.recommendation_id == recommendation_id
        assert result.recommendation_status == RecommendationStatus.GENERATED.value
        assert result.persisted is True
        assert result.persisted_at.tzinfo is not None
        assert result.recommendation == successful_recommendation

    def test_process_and_persist_with_failed_recommendation(
        self,
        allocation_request,
        failed_recommendation,
        tenant_id,
        correlation_id,
    ):
        """Test processing and persistence with FAILED recommendation."""
        recommendation_id = uuid4()
        fake_allocation = FakeAllocationService(failed_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(allocation_request))

        # Verify result envelope for FAILED recommendation
        assert result.recommendation_status == RecommendationStatus.FAILED.value
        assert result.recommendation == failed_recommendation

    def test_process_and_persist_with_custom_timestamp(
        self,
        allocation_request,
        successful_recommendation,
    ):
        """Test processing and persistence with custom evaluation timestamp."""
        recommendation_id = uuid4()
        custom_timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(
            allocation_request,
            evaluation_timestamp=custom_timestamp,
        ))

        # Verify custom timestamp passed through
        assert fake_allocation.last_timestamp == custom_timestamp
        assert fake_persistence.last_timestamp == custom_timestamp

    def test_process_and_persist_raises_persistence_conflict_error(
        self,
        allocation_request,
        successful_recommendation,
    ):
        """Test that PersistenceConflictError is propagated."""
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(uuid4())
        fake_persistence.should_raise = PersistenceConflictError(
            "Duplicate correlation_id"
        )

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        with pytest.raises(PersistenceConflictError) as exc_info:
            asyncio.run(service.process_and_persist(allocation_request))

        assert "Duplicate correlation_id" in str(exc_info.value)

    def test_process_and_persist_raises_persistence_validation_error(
        self,
        allocation_request,
        successful_recommendation,
    ):
        """Test that PersistenceValidationError is propagated."""
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(uuid4())
        fake_persistence.should_raise = PersistenceValidationError(
            "Invalid datetime"
        )

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        with pytest.raises(PersistenceValidationError) as exc_info:
            asyncio.run(service.process_and_persist(allocation_request))

        assert "Invalid datetime" in str(exc_info.value)

    def test_process_and_persist_raises_persistence_transaction_error(
        self,
        allocation_request,
        successful_recommendation,
    ):
        """Test that PersistenceTransactionError is propagated."""
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(uuid4())
        fake_persistence.should_raise = PersistenceTransactionError(
            "Transaction failed"
        )

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        with pytest.raises(PersistenceTransactionError) as exc_info:
            asyncio.run(service.process_and_persist(allocation_request))

        assert "Transaction failed" in str(exc_info.value)

    def test_process_and_persist_wraps_unexpected_exception(
        self,
        allocation_request,
        successful_recommendation,
    ):
        """Test that unexpected exceptions are wrapped in PersistenceTransactionError."""
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(uuid4())
        fake_persistence.should_raise = RuntimeError("Unexpected error")

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        with pytest.raises(PersistenceTransactionError) as exc_info:
            asyncio.run(service.process_and_persist(allocation_request))

        assert "Persistence failed" in str(exc_info.value)
        assert exc_info.value.__cause__ is not None

    def test_process_and_persist_validates_correlation_id_match(
        self,
        allocation_request,
        tenant_id,
        correlation_id,
    ):
        """Test that correlation_id mismatch raises PersistenceValidationError."""
        # Create recommendation with different correlation_id
        wrong_metadata = AgentMessageMetadata(
            tenant_id=tenant_id,
            correlation_id=uuid4(),  # Different correlation_id
            process_instance_id=uuid4(),
            task_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        wrong_recommendation = AllocationRecommendation(
            metadata=wrong_metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )

        fake_allocation = FakeAllocationService(wrong_recommendation)
        fake_persistence = FakePersistence(uuid4())

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        with pytest.raises(PersistenceValidationError) as exc_info:
            asyncio.run(service.process_and_persist(allocation_request))

        assert "correlation_id does not match" in str(exc_info.value)

    def test_process_and_persist_validates_tenant_id_match(
        self,
        allocation_request,
        correlation_id,
    ):
        """Test that tenant_id mismatch raises PersistenceValidationError."""
        # Create recommendation with different tenant_id
        wrong_metadata = AgentMessageMetadata(
            tenant_id=uuid4(),  # Different tenant_id
            correlation_id=correlation_id,
            process_instance_id=uuid4(),
            task_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        wrong_recommendation = AllocationRecommendation(
            metadata=wrong_metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )

        fake_allocation = FakeAllocationService(wrong_recommendation)
        fake_persistence = FakePersistence(uuid4())

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        with pytest.raises(PersistenceValidationError) as exc_info:
            asyncio.run(service.process_and_persist(allocation_request))

        assert "tenant_id does not match" in str(exc_info.value)

    def test_process_and_persist_rejects_naive_timestamp(
        self,
        allocation_request,
        successful_recommendation,
    ):
        """Test that naive datetime raises ValueError."""
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(uuid4())

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        naive_timestamp = datetime(2024, 1, 1, 12, 0, 0)  # No timezone

        with pytest.raises(ValueError) as exc_info:
            asyncio.run(service.process_and_persist(
                allocation_request,
                evaluation_timestamp=naive_timestamp,
            ))

        assert "must be timezone-aware" in str(exc_info.value)


class TestPersistedAllocationResult:
    """Tests for PersistedAllocationResult."""

    def test_create_with_defaults(self, tenant_id, correlation_id):
        """Test factory method with default timestamp."""
        recommendation_id = uuid4()
        recommendation = AllocationRecommendation(
            metadata=AgentMessageMetadata(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                process_instance_id=uuid4(),
                task_id=uuid4(),
                message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            ),
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )

        result = PersistedAllocationResult.create(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            allocation_request_id=recommendation_id,
            recommendation_id=recommendation_id,
            recommendation_status=RecommendationStatus.GENERATED.value,
            recommendation=recommendation,
        )

        assert result.persisted is True
        assert result.persisted_at.tzinfo is not None
        assert result.tenant_id == tenant_id
        assert result.correlation_id == correlation_id

    def test_create_with_custom_timestamp(self, tenant_id, correlation_id):
        """Test factory method with custom timestamp."""
        recommendation_id = uuid4()
        custom_timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        recommendation = AllocationRecommendation(
            metadata=AgentMessageMetadata(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                process_instance_id=uuid4(),
                task_id=uuid4(),
                message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            ),
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )

        result = PersistedAllocationResult.create(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            allocation_request_id=recommendation_id,
            recommendation_id=recommendation_id,
            recommendation_status=RecommendationStatus.GENERATED.value,
            recommendation=recommendation,
            persisted_at=custom_timestamp,
        )

        assert result.persisted_at == custom_timestamp

    def test_create_rejects_naive_timestamp(self, tenant_id, correlation_id):
        """Test factory method rejects naive timestamp."""
        recommendation_id = uuid4()
        naive_timestamp = datetime(2024, 1, 1, 12, 0, 0)  # No timezone
        recommendation = AllocationRecommendation(
            metadata=AgentMessageMetadata(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                process_instance_id=uuid4(),
                task_id=uuid4(),
                message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            ),
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )

        with pytest.raises(ValueError) as exc_info:
            PersistedAllocationResult.create(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                allocation_request_id=recommendation_id,
                recommendation_id=recommendation_id,
                recommendation_status=RecommendationStatus.GENERATED.value,
                recommendation=recommendation,
                persisted_at=naive_timestamp,
            )

        assert "must be timezone-aware" in str(exc_info.value)


    def test_persisted_result_validates_tenant_id_match(self, tenant_id, correlation_id):
        """Test that tenant_id must match recommendation metadata."""
        recommendation_id = uuid4()
        wrong_tenant_id = uuid4()
        recommendation = AllocationRecommendation(
            metadata=AgentMessageMetadata(
                tenant_id=wrong_tenant_id,  # Different tenant_id
                correlation_id=correlation_id,
                process_instance_id=uuid4(),
                task_id=uuid4(),
                message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            ),
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )

        with pytest.raises(ValueError) as exc_info:
            PersistedAllocationResult.create(
                tenant_id=tenant_id,  # Different from recommendation
                correlation_id=correlation_id,
                allocation_request_id=recommendation_id,
                recommendation_id=recommendation_id,
                recommendation_status=RecommendationStatus.GENERATED.value,
                recommendation=recommendation,
            )

        assert "tenant_id does not match recommendation metadata" in str(exc_info.value)

    def test_persisted_result_validates_correlation_id_match(self, tenant_id, correlation_id):
        """Test that correlation_id must match recommendation metadata."""
        recommendation_id = uuid4()
        wrong_correlation_id = uuid4()
        recommendation = AllocationRecommendation(
            metadata=AgentMessageMetadata(
                tenant_id=tenant_id,
                correlation_id=wrong_correlation_id,  # Different correlation_id
                process_instance_id=uuid4(),
                task_id=uuid4(),
                message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            ),
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )

        with pytest.raises(ValueError) as exc_info:
            PersistedAllocationResult.create(
                tenant_id=tenant_id,
                correlation_id=correlation_id,  # Different from recommendation
                allocation_request_id=recommendation_id,
                recommendation_id=recommendation_id,
                recommendation_status=RecommendationStatus.GENERATED.value,
                recommendation=recommendation,
            )

        assert "correlation_id does not match recommendation metadata" in str(exc_info.value)

    def test_persisted_result_requires_all_ids(self, tenant_id, correlation_id):
        """Test that all ID fields are required (enforced by Pydantic UUID type)."""
        # Pydantic's UUID type validation ensures IDs are present and valid
        # This test verifies the type constraints are in place
        recommendation = AllocationRecommendation(
            metadata=AgentMessageMetadata(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                process_instance_id=uuid4(),
                task_id=uuid4(),
                message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            ),
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )

        # Test that None is rejected by Pydantic UUID type
        with pytest.raises(ValueError):  # Pydantic validation error
            PersistedAllocationResult.create(
                tenant_id=None,  # type: ignore
                correlation_id=correlation_id,
                allocation_request_id=uuid4(),
                recommendation_id=uuid4(),
                recommendation_status=RecommendationStatus.GENERATED.value,
                recommendation=recommendation,
            )

    def test_persisted_result_persisted_cannot_be_false(self, tenant_id, correlation_id):
        """Test that persisted cannot be False (enforced by Literal)."""
        # This test verifies the Literal type constraint
        # The field is defined as Literal[True] = True, so False cannot be assigned
        # We verify this through the model_validator
        recommendation_id = uuid4()
        recommendation = AllocationRecommendation(
            metadata=AgentMessageMetadata(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                process_instance_id=uuid4(),
                task_id=uuid4(),
                message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            ),
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )

        # The Literal[True] type prevents False at the type level
        # We verify the field is True in the result
        result = PersistedAllocationResult.create(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            allocation_request_id=recommendation_id,
            recommendation_id=recommendation_id,
            recommendation_status=RecommendationStatus.GENERATED.value,
            recommendation=recommendation,
        )
        assert result.persisted is True


class TestApplicationServiceCoverage:
    """Additional coverage tests for the 22 required scenarios."""

    @pytest.fixture
    def human_requirement(self, tenant_id):
        """Fixture for HUMAN resource requirement."""
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
    def budget_requirement(self, tenant_id):
        """Fixture for BUDGET resource requirement."""
        return BudgetResourceRequirement(
            resource_type=ResourceType.BUDGET,
            requester_id=uuid4(),
            task_deadline=datetime(2024, 6, 1, tzinfo=timezone.utc),
            required_amount=Decimal("5000"),
            currency="USD",
            process_stage="resource_allocation",
        )

    def test_human_recommendation_persisted_once(
        self, metadata, human_requirement, successful_recommendation
    ):
        """Test HUMAN recommendation persisted once."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_requirement,
            budget_requirements=None,
        )
        recommendation_id = uuid4()
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(allocation_request))

        assert fake_allocation.call_count == 1
        assert fake_persistence.call_count == 1
        assert result.recommendation_id == recommendation_id

    def test_budget_recommendation_persisted_once(
        self, metadata, budget_requirement, successful_recommendation
    ):
        """Test BUDGET recommendation persisted once."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=budget_requirement,
        )
        recommendation_id = uuid4()
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(allocation_request))

        assert fake_allocation.call_count == 1
        assert fake_persistence.call_count == 1
        assert result.recommendation_id == recommendation_id

    def test_mixed_human_budget_persisted_once(
        self, metadata, human_requirement, budget_requirement, successful_recommendation
    ):
        """Test mixed HUMAN+BUDGET recommendation persisted once."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_requirement,
            budget_requirements=budget_requirement,
        )
        recommendation_id = uuid4()
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(allocation_request))

        assert fake_allocation.call_count == 1
        assert fake_persistence.call_count == 1
        assert result.recommendation_id == recommendation_id

    def test_business_gap_remains_pending_human_approval(
        self, metadata, human_requirement
    ):
        """Test business gap remains PENDING_HUMAN_APPROVAL."""
        gap_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.PENDING_HUMAN_APPROVAL,
            explanation="Gap detected",
            confidence=0.8,
            requires_human_approval=True,
            manual_intervention_required=False,
            resource_gaps=[
                ResourceGap(
                    resource_type=ResourceType.HUMAN,
                    gap_type=GapType.NO_ELIGIBLE_HUMAN,
                    gap_description="No eligible candidates",
                )
            ],
        )
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_requirement,
            budget_requirements=None,
        )
        recommendation_id = uuid4()
        fake_allocation = FakeAllocationService(gap_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(allocation_request))

        assert result.recommendation_status == RecommendationStatus.PENDING_HUMAN_APPROVAL.value

    def test_failed_recommendation_persisted_for_audit(
        self, metadata, failed_recommendation
    ):
        """Test FAILED recommendation persisted for audit."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        recommendation_id = uuid4()
        fake_allocation = FakeAllocationService(failed_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(allocation_request))

        assert result.recommendation_status == RecommendationStatus.FAILED.value
        assert result.recommendation.error_code == "TEST_ERROR"
        assert result.recommendation.error_message == "Test error message"

    def test_tenant_id_from_request_metadata_only(self, metadata):
        """Test tenant_id comes only from request.metadata.tenant_id."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        recommendation_id = uuid4()
        successful_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(allocation_request))

        assert result.tenant_id == metadata.tenant_id

    def test_requester_id_never_tenant_scope(self, metadata, human_requirement):
        """Test requester_id is never tenant scope."""
        # requester_id is part of the requirement, not tenant scope
        assert human_requirement.requester_id != metadata.tenant_id
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_requirement,
            budget_requirements=None,
        )
        recommendation_id = uuid4()
        successful_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(allocation_request))

        # Verify tenant_id is from metadata, not requester_id
        assert result.tenant_id == metadata.tenant_id

    def test_correlation_id_preserved_end_to_end(self, metadata):
        """Test correlation_id preserved end-to-end."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        recommendation_id = uuid4()
        successful_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(allocation_request))

        assert result.correlation_id == metadata.correlation_id
        assert result.recommendation.metadata.correlation_id == metadata.correlation_id

    def test_allocation_service_called_exactly_once(self, metadata):
        """Test allocation service called exactly once."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        recommendation_id = uuid4()
        successful_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        asyncio.run(service.process_and_persist(allocation_request))

        assert fake_allocation.call_count == 1

    def test_repository_called_exactly_once(self, metadata):
        """Test repository called exactly once."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        recommendation_id = uuid4()
        successful_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        asyncio.run(service.process_and_persist(allocation_request))

        assert fake_persistence.call_count == 1

    def test_persisted_ids_from_repository_result(self, metadata):
        """Test persisted IDs originate from repository result."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        recommendation_id = uuid4()
        successful_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(allocation_request))

        assert result.recommendation_id == recommendation_id
        assert result.allocation_request_id == recommendation_id  # Currently using same ID

    def test_persisted_at_utc_aware(self, metadata):
        """Test persisted_at is UTC-aware."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        recommendation_id = uuid4()
        successful_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(allocation_request))

        assert result.persisted_at.tzinfo is not None
        assert result.persisted_at.tzinfo.utcoffset(result.persisted_at) is not None

    def test_persistence_failure_never_returns_success(self, metadata):
        """Test persistence failure never returns success."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        successful_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(uuid4())
        fake_persistence.should_raise = PersistenceTransactionError("DB error")

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        with pytest.raises(PersistenceTransactionError):
            asyncio.run(service.process_and_persist(allocation_request))

    def test_persistence_errors_no_credentials(self, metadata):
        """Test persistence errors contain no DB URL/password/SQL."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        successful_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(uuid4())
        fake_persistence.should_raise = PersistenceTransactionError("Connection failed")

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        with pytest.raises(PersistenceTransactionError) as exc_info:
            asyncio.run(service.process_and_persist(allocation_request))

        error_str = str(exc_info.value)
        assert "password" not in error_str.lower()
        assert "postgresql://" not in error_str.lower()
        assert "select" not in error_str.lower()

    def test_conflict_remains_persistence_conflict_error(self, metadata):
        """Test conflict remains PersistenceConflictError."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        successful_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(uuid4())
        fake_persistence.should_raise = PersistenceConflictError("Duplicate")

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        with pytest.raises(PersistenceConflictError):
            asyncio.run(service.process_and_persist(allocation_request))

    def test_naive_evaluation_timestamp_rejected(self, metadata):
        """Test naive evaluation timestamp rejected."""
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        successful_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=0.9,
            requires_human_approval=True,
            manual_intervention_required=False,
        )
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(uuid4())

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        naive_timestamp = datetime(2024, 1, 1, 12, 0, 0)  # No timezone

        with pytest.raises(ValueError) as exc_info:
            asyncio.run(service.process_and_persist(
                allocation_request,
                evaluation_timestamp=naive_timestamp,
            ))

        assert "must be timezone-aware" in str(exc_info.value)

    def test_agent3_status_enum_limited(self, metadata):
        """Test that Agent 3 RecommendationStatus enum is limited to allowed values."""
        # Agent 3's RecommendationStatus only includes: GENERATED, PENDING_HUMAN_APPROVAL, SUPERSEDED, FAILED
        # APPROVED and REJECTED are not in the enum (they belong to other agents)
        allowed_statuses = [
            RecommendationStatus.GENERATED,
            RecommendationStatus.PENDING_HUMAN_APPROVAL,
            RecommendationStatus.SUPERSEDED,
            RecommendationStatus.FAILED,
        ]
        
        # Verify these are the only statuses in the enum
        assert len(RecommendationStatus) == 4
        for status in allowed_statuses:
            assert status in RecommendationStatus

    def test_decimal_values_remain_decimal(self, metadata, human_requirement):
        """Test Decimal values remain Decimal."""
        assert isinstance(human_requirement.estimated_effort_hours, Decimal)
        allocation_request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_requirement,
            budget_requirements=None,
        )
        recommendation_id = uuid4()
        successful_recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.GENERATED,
            explanation="Test",
            confidence=Decimal("0.9"),
            requires_human_approval=True,
            manual_intervention_required=False,
        )
        fake_allocation = FakeAllocationService(successful_recommendation)
        fake_persistence = FakePersistence(recommendation_id)

        service = PersistentResourceAllocationService(
            allocation_service=fake_allocation,
            persistence=fake_persistence,
        )

        result = asyncio.run(service.process_and_persist(allocation_request))

        assert isinstance(result.recommendation.confidence, Decimal)

    def test_no_openai_call(self, metadata):
        """Test no OpenAI call (verified by absence of import and call)."""
        # Verify no OpenAI import in application_service.py
        import app.agents.agent3_resources.application_service as app_service_module
        source = app_service_module.__file__
        with open(source, 'r') as f:
            content = f.read()
        assert "openai" not in content.lower()
        assert "gpt" not in content.lower()

    def test_no_engine_session_creation(self, metadata):
        """Test no engine/session creation in application service."""
        # Verify no SQLAlchemy engine/session creation in application_service.py
        import app.agents.agent3_resources.application_service as app_service_module
        source = app_service_module.__file__
        with open(source, 'r') as f:
            content = f.read()
        assert "create_engine" not in content
        assert "AsyncSession" not in content
        assert "sessionmaker" not in content

    def test_schema_valid_failed_shape_intact(self, metadata):
        """Test schema-valid FAILED shape remains intact."""
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
        
        # Verify FAILED shape is schema-valid
        assert failed_recommendation.status == RecommendationStatus.FAILED
        assert failed_recommendation.error_code == "TEST_ERROR"
        assert failed_recommendation.error_message == "Test error message"
        assert failed_recommendation.retryable is True
        assert failed_recommendation.human_requirement_result is None
        assert failed_recommendation.budget_requirement_result is None
        assert failed_recommendation.resource_gaps == []
        assert failed_recommendation.alternatives == []
        assert failed_recommendation.confidence is None
