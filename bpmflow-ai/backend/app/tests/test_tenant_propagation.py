"""Tests for trusted tenant_id propagation through Agent 3."""

import pytest
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

pytestmark = pytest.mark.anyio

from app.agents.agent3_resources import (
    ResourceAllocationService,
    HumanResourceStrategy,
    BudgetResourceStrategy,
    InMemoryResourceRepository,
    AllocationRequest,
    AgentMessageMetadata,
    HumanResourceRequirement,
    BudgetResourceRequirement,
    MessageType,
    ResourceType,
    create_human_evidence,
    create_budget_evidence,
    get_tenant_a_id,
    get_requester_id,
    get_resource_id_1,
)


class TenantTrackingRepository(InMemoryResourceRepository):
    """Repository that records tenant_id used for discovery lookups."""

    def __init__(self):
        super().__init__()
        self.human_lookup_tenant_ids = []
        self.budget_lookup_tenant_ids = []

    async def get_human_resources_by_tenant(self, tenant_id, evaluation_timestamp):
        self.human_lookup_tenant_ids.append(tenant_id)
        return await super().get_human_resources_by_tenant(tenant_id, evaluation_timestamp)

    async def get_budget_resources_by_tenant(self, tenant_id, evaluation_timestamp):
        self.budget_lookup_tenant_ids.append(tenant_id)
        return await super().get_budget_resources_by_tenant(tenant_id, evaluation_timestamp)


def _request_metadata(tenant_id, correlation_id=None) -> AgentMessageMetadata:
    return AgentMessageMetadata(
        correlation_id=correlation_id or uuid4(),
        process_instance_id=uuid4(),
        task_id=uuid4(),
        tenant_id=tenant_id,
        message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
    )


class TestTenantPropagation:
    """Tenant scope must come from metadata, never from requester_id."""

    async def test_tenant_and_requester_may_differ_for_human_discovery(
        self, evaluation_timestamp
    ):
        repository = TenantTrackingRepository()
        repository.add_human_resource(
            create_human_evidence(
                tenant_id=get_tenant_a_id(),
                reference_timestamp=evaluation_timestamp,
                resource_id=get_resource_id_1(),
                roles=["developer"],
                mandatory_skills=["python"],
            )
        )
        strategy = HumanResourceStrategy(repository)
        requirement = HumanResourceRequirement(
            requester_id=get_requester_id(),
            task_deadline=evaluation_timestamp + timedelta(days=30),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )

        assert get_requester_id() != get_tenant_a_id()

        result = await strategy.process_requirement(
            requirement,
            tenant_id=get_tenant_a_id(),
            evaluation_timestamp=evaluation_timestamp,
        )

        assert repository.human_lookup_tenant_ids == [get_tenant_a_id()]
        assert get_requester_id() not in repository.human_lookup_tenant_ids
        assert len(result.eligible_candidates) == 1

    async def test_tenant_and_requester_may_differ_for_budget_discovery(
        self, evaluation_timestamp
    ):
        repository = TenantTrackingRepository()
        repository.add_budget_resource(
            create_budget_evidence(
                tenant_id=get_tenant_a_id(),
                reference_timestamp=evaluation_timestamp,
                available_balance=Decimal("10000"),
                currency="USD",
                cost_centre="CC001",
            )
        )
        strategy = BudgetResourceStrategy(repository)
        requirement = BudgetResourceRequirement(
            required_amount=Decimal("5000"),
            currency="USD",
            cost_centre="CC001",
            requester_id=get_requester_id(),
            task_deadline=evaluation_timestamp + timedelta(days=30),
            process_stage="resource_allocation",
        )

        result = await strategy.process_requirement(
            requirement,
            tenant_id=get_tenant_a_id(),
            evaluation_timestamp=evaluation_timestamp,
        )

        assert repository.budget_lookup_tenant_ids == [get_tenant_a_id()]
        assert get_requester_id() not in repository.budget_lookup_tenant_ids
        assert result.budget_validation is not None
        assert result.budget_validation.sufficient_balance is True

    async def test_service_uses_metadata_tenant_not_requester_id(
        self, evaluation_timestamp
    ):
        repository = TenantTrackingRepository()
        repository.add_human_resource(
            create_human_evidence(
                tenant_id=get_tenant_a_id(),
                reference_timestamp=evaluation_timestamp,
                resource_id=get_resource_id_1(),
                roles=["developer"],
                mandatory_skills=["python"],
            )
        )
        service = ResourceAllocationService(repository)
        correlation_id = uuid4()
        request = AllocationRequest(
            metadata=_request_metadata(get_tenant_a_id(), correlation_id=correlation_id),
            human_requirements=HumanResourceRequirement(
                required_roles=["developer"],
                mandatory_skills=["python"],
                requester_id=get_requester_id(),
                task_deadline=evaluation_timestamp + timedelta(days=30),
                estimated_effort_hours=Decimal("10"),
                process_stage="resource_allocation",
            ),
        )

        recommendation = await service.process_allocation_request(
            request,
            evaluation_timestamp,
        )

        assert repository.human_lookup_tenant_ids == [get_tenant_a_id()]
        assert get_requester_id() not in repository.human_lookup_tenant_ids
        assert len(recommendation.human_requirement_result.eligible_candidates) == 1
        assert recommendation.metadata.correlation_id == correlation_id

    async def test_wrong_tenant_remains_invisible_when_requester_differs(
        self, evaluation_timestamp
    ):
        repository = InMemoryResourceRepository()
        repository.add_human_resource(
            create_human_evidence(
                tenant_id=get_tenant_a_id(),
                reference_timestamp=evaluation_timestamp,
                resource_id=get_resource_id_1(),
                roles=["developer"],
                mandatory_skills=["python"],
            )
        )
        service = ResourceAllocationService(repository)
        request = AllocationRequest(
            metadata=_request_metadata(get_requester_id()),
            human_requirements=HumanResourceRequirement(
                requester_id=get_requester_id(),
                task_deadline=evaluation_timestamp + timedelta(days=30),
                estimated_effort_hours=Decimal("10"),
                process_stage="resource_allocation",
            ),
        )

        recommendation = await service.process_allocation_request(
            request,
            evaluation_timestamp,
        )

        assert recommendation.human_requirement_result.eligible_candidates == []
        assert len(recommendation.resource_gaps) > 0
