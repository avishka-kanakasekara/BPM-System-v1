"""Integration tests for Agent 3 Resource Allocation."""

import pytest
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

pytestmark = pytest.mark.anyio

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
    get_tenant_a_id,
    get_requester_id,
    get_resource_id_1,
    get_resource_id_2,
)


def _task_deadline(evaluation_timestamp):
    return evaluation_timestamp + timedelta(days=150)


def _human_resource(evaluation_timestamp, **overrides):
    return create_human_evidence(
        tenant_id=get_requester_id(),
        reference_timestamp=evaluation_timestamp,
        **overrides,
    )


def _budget_resource(evaluation_timestamp, **overrides):
    return create_budget_evidence(
        tenant_id=get_requester_id(),
        reference_timestamp=evaluation_timestamp,
        **overrides,
    )


class TestAgent3Integration:
    """Integration tests for complete Agent 3 pipeline."""

    async def test_end_to_end_human_resource_allocation(self, evaluation_timestamp):
        """Test complete end-to-end HUMAN resource allocation."""
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)
        
        # Add multiple human resources
        resource1 = _human_resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            name="Senior Developer",
            is_active=True,
            roles=["developer"],
            mandatory_skills=["python", "fastapi"],
            preferred_skills=["docker"],
            authority="senior",
            current_workload=Decimal("30"),
            max_workload=Decimal("100"),
        )
        repository.add_human_resource(resource1)

        resource2 = _human_resource(
            evaluation_timestamp,
            resource_id=get_resource_id_2(),
            name="Junior Developer",
            is_active=True,
            roles=["developer"],
            mandatory_skills=["python"],
            preferred_skills=[],
            authority="junior",
            current_workload=Decimal("50"),
            max_workload=Decimal("100"),
        )
        repository.add_human_resource(resource2)
        
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
            task_deadline=_task_deadline(evaluation_timestamp),
            estimated_effort_hours=Decimal("20"),
            process_stage="resource_allocation",
        )
        
        request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_req,
        )
        
        # Process request
        recommendation = await service.process_allocation_request(request, evaluation_timestamp)
        
        # Verify end-to-end results
        assert recommendation.status == RecommendationStatus.PENDING_HUMAN_APPROVAL
        assert recommendation.requires_human_approval is True
        assert recommendation.human_requirement_result is not None
        assert len(recommendation.human_requirement_result.eligible_candidates) > 0
        assert recommendation.explanation is not None
        assert "Senior Developer" in recommendation.explanation

    async def test_end_to_end_budget_validation(self, evaluation_timestamp):
        """Test complete end-to-end BUDGET validation."""
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)
        
        # Add budget resource
        repository.add_budget_resource(
            _budget_resource(
                evaluation_timestamp,
                name="Team Budget 2026",
                available_balance=Decimal("50000"),
                currency="USD",
                cost_centre="CC001",
                authorization_limit=Decimal("100000"),
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
            required_amount=Decimal("25000"),
            currency="USD",
            cost_centre="CC001",
            requester_id=get_requester_id(),
            task_deadline=_task_deadline(evaluation_timestamp),
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
        assert recommendation.budget_requirement_result.budget_validation.within_authorization_limit is True

    async def test_end_to_end_combined_human_and_budget(self, evaluation_timestamp):
        """Test end-to-end with both HUMAN and BUDGET requirements."""
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)
        
        # Add resources
        human_resource = _human_resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            is_active=True,
            roles=["developer"],
            mandatory_skills=["python"],
        )
        repository.add_human_resource(human_resource)

        repository.add_budget_resource(
            _budget_resource(
                evaluation_timestamp,
                available_balance=Decimal("10000"),
                currency="USD",
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
            task_deadline=_task_deadline(evaluation_timestamp),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )
        
        budget_req = BudgetResourceRequirement(
            resource_type=ResourceType.BUDGET,
            required_amount=Decimal("5000"),
            currency="USD",
            requester_id=get_requester_id(),
            task_deadline=_task_deadline(evaluation_timestamp),
            process_stage="resource_allocation",
        )
        
        request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_req,
            budget_requirements=budget_req,
        )
        
        recommendation = await service.process_allocation_request(request, evaluation_timestamp)
        
        # Verify both results
        assert recommendation.human_requirement_result is not None
        assert recommendation.budget_requirement_result is not None
        assert recommendation.explanation is not None

    async def test_end_to_end_gap_detection_and_alternatives(self, evaluation_timestamp):
        """Test end-to-end gap detection with alternatives."""
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)

        resource = _human_resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            is_active=False,
        )
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
            task_deadline=_task_deadline(evaluation_timestamp),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_req,
        )

        recommendation = await service.process_allocation_request(request, evaluation_timestamp)

        assert recommendation.status == RecommendationStatus.PENDING_HUMAN_APPROVAL
        assert len(recommendation.resource_gaps) > 0
        assert len(recommendation.alternatives) > 0
        assert len(recommendation.limitations) > 0
        assert "Suggested Alternatives" in recommendation.explanation

    async def test_end_to_end_message_contract_preservation(self, evaluation_timestamp):
        """Test that message contract is preserved through pipeline."""
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)
        
        correlation_id = uuid4()
        process_instance_id = uuid4()
        task_id = uuid4()
        
        repository.add_human_resource(
            _human_resource(
                evaluation_timestamp,
                resource_id=get_resource_id_1(),
            )
        )
        
        metadata = AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=process_instance_id,
            task_id=task_id,
            tenant_id=get_requester_id(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        
        human_req = HumanResourceRequirement(
            resource_type=ResourceType.HUMAN,
            requester_id=get_requester_id(),
            task_deadline=_task_deadline(evaluation_timestamp),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )
        
        request = AllocationRequest(
            metadata=metadata,
            human_requirements=human_req,
        )
        
        recommendation = await service.process_allocation_request(request, evaluation_timestamp)
        
        # Verify contract preservation
        assert recommendation.metadata.correlation_id == correlation_id
        assert recommendation.metadata.process_instance_id == process_instance_id
        assert recommendation.metadata.task_id == task_id
        assert recommendation.metadata.tenant_id == get_requester_id()
        assert recommendation.metadata.message_type == MessageType.RESOURCE_ALLOCATION_RESPONSE
