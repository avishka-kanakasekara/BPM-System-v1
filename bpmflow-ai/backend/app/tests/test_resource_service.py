"""Tests for resource allocation service orchestration."""

import pytest
from datetime import timezone
from decimal import Decimal
from uuid import uuid4

pytestmark = pytest.mark.anyio

from app.tests.conftest import utc_datetime

from app.agents.agent3_resources import (
    ResourceAllocationService,
    InMemoryResourceRepository,
    AllocationRequest,
    AgentMessageMetadata,
    HumanResourceRequirement,
    BudgetResourceRequirement,
    RecommendationStatus,
    MessageType,
    ResourceType,
    create_human_evidence,
    create_budget_evidence,
    get_requester_id,
    get_resource_id_1,
    get_tenant_a_id,
    get_tenant_b_id,
)


class TestResourceService:
    """Test resource allocation service orchestration."""

    async def test_service_happy_path(self, evaluation_timestamp):
        """Test complete service happy path with eligible candidates."""
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)
        
        # Add eligible human resource
        from datetime import timedelta
        resource = create_human_evidence(
            tenant_id=get_requester_id(),  # Use requester_id for consistency
            resource_id=get_resource_id_1(),
            is_active=True,
            roles=["developer"],
            mandatory_skills=["python"],
            preferred_skills=["fastapi"],
            authority="senior",
            current_workload=Decimal("30"),
            max_workload=Decimal("100"),
        )
        # Set available_from to be before the task deadline
        resource.available_from = utc_datetime(2026, 5, 1)
        repository.add_human_resource(resource)
        
        # Create request
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=get_requester_id(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        
        human_req = HumanResourceRequirement(
            resource_type=ResourceType.HUMAN,
            required_roles=["developer"],
            mandatory_skills=["python"],
            preferred_skills=["fastapi"],
            required_authority="senior",
            requester_id=get_requester_id(),
            task_deadline=utc_datetime(2026, 6, 1),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )
        
        request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_req,
        )
        
        # Process request
        recommendation = await service.process_allocation_request(request, evaluation_timestamp)
        
        # Verify results
        assert recommendation.status == RecommendationStatus.PENDING_HUMAN_APPROVAL
        assert recommendation.requires_human_approval is True
        assert recommendation.human_requirement_result is not None
        assert len(recommendation.human_requirement_result.eligible_candidates) > 0
        assert len(recommendation.resource_gaps) == 0
        assert recommendation.explanation is not None
        assert recommendation.confidence > Decimal("0")

    async def test_service_no_eligible_human_returns_failed(self, evaluation_timestamp):
        """Test service returns FAILED when no eligible HUMAN resources exist."""
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)

        repository.add_human_resource(
            create_human_evidence(
                tenant_id=get_requester_id(),
                resource_id=get_resource_id_1(),
                is_active=False,
            )
        )

        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=get_requester_id(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )

        human_req = HumanResourceRequirement(
            resource_type=ResourceType.HUMAN,
            requester_id=get_requester_id(),
            task_deadline=utc_datetime(2026, 6, 1),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_req,
        )

        recommendation = await service.process_allocation_request(request, evaluation_timestamp)

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == "NO_ELIGIBLE_CANDIDATES"
        assert recommendation.retryable is True
        assert recommendation.human_requirement_result is None
        assert recommendation.resource_gaps == []

    async def test_service_budget_validation(self, evaluation_timestamp):
        """Test service budget validation."""
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)
        
        # Add budget resource
        repository.add_budget_resource(
            create_budget_evidence(
                tenant_id=get_requester_id(),
                available_balance=Decimal("10000"),
                currency="USD",
                cost_centre="CC001",
            )
        )
        
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=get_requester_id(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        
        budget_req = BudgetResourceRequirement(
            resource_type=ResourceType.BUDGET,
            required_amount=Decimal("5000"),
            currency="USD",
            cost_centre="CC001",
            requester_id=get_requester_id(),
            task_deadline=utc_datetime(2026, 6, 1),
            process_stage="resource_allocation",
        )
        
        request = AllocationRequest(
            metadata=metadata,
            budget_requirements=budget_req,
        )
        
        recommendation = await service.process_allocation_request(request, evaluation_timestamp)
        
        # Verify budget validation
        assert recommendation.budget_requirement_result is not None
        assert recommendation.budget_requirement_result.budget_validation is not None
        assert recommendation.budget_requirement_result.budget_validation.sufficient_balance is True

    async def test_service_preserves_correlation_id(self, evaluation_timestamp):
        """Test that service preserves correlation ID."""
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)
        
        correlation_id = uuid4()
        
        metadata = AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=get_requester_id(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        
        human_req = HumanResourceRequirement(
            resource_type=ResourceType.HUMAN,
            requester_id=get_requester_id(),
            task_deadline=utc_datetime(2026, 6, 1),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )
        
        request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_req,
        )
        
        recommendation = await service.process_allocation_request(request, evaluation_timestamp)
        
        assert recommendation.metadata.correlation_id == correlation_id

    async def test_service_human_approval_always_required(self, evaluation_timestamp):
        """Test that service always requires human approval."""
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)

        resource = create_human_evidence(
            tenant_id=get_requester_id(),
            resource_id=get_resource_id_1(),
        )
        resource.available_from = utc_datetime(2025, 12, 1)
        repository.add_human_resource(resource)

        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=get_requester_id(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        
        human_req = HumanResourceRequirement(
            resource_type=ResourceType.HUMAN,
            requester_id=get_requester_id(),
            task_deadline=utc_datetime(2026, 6, 1),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )
        
        request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_req,
        )
        
        recommendation = await service.process_allocation_request(request, evaluation_timestamp)
        
        assert recommendation.requires_human_approval is True
        assert recommendation.status == RecommendationStatus.PENDING_HUMAN_APPROVAL

    async def test_service_generates_explanation(self, evaluation_timestamp):
        """Test that service generates template explanation."""
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)
        
        repository.add_human_resource(
            create_human_evidence(
                tenant_id=get_requester_id(),
                resource_id=get_resource_id_1(),
            )
        )
        repository._human_resources[-1].available_from = utc_datetime(2025, 12, 1)
        
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=get_requester_id(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        
        human_req = HumanResourceRequirement(
            resource_type=ResourceType.HUMAN,
            requester_id=get_requester_id(),
            task_deadline=utc_datetime(2026, 6, 1),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )
        
        request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_req,
        )
        
        recommendation = await service.process_allocation_request(request, evaluation_timestamp)
        
        assert recommendation.explanation is not None
        assert len(recommendation.explanation) > 0
        assert "Approval Required" in recommendation.explanation

    async def test_service_cross_tenant_isolation(self, evaluation_timestamp):
        """Test that service respects cross-tenant isolation."""
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)
        
        # Add resource for tenant A
        repository.add_human_resource(
            create_human_evidence(
                tenant_id=get_tenant_a_id(),
                resource_id=get_resource_id_1(),
            )
        )
        
        # Request from tenant B
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),  # Different tenant
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        
        human_req = HumanResourceRequirement(
            resource_type=ResourceType.HUMAN,
            requester_id=get_requester_id(),
            task_deadline=utc_datetime(2026, 6, 1),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )
        
        request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_req,
        )
        
        recommendation = await service.process_allocation_request(request, evaluation_timestamp)

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == "NO_ELIGIBLE_CANDIDATES"
        assert recommendation.human_requirement_result is None
