"""Contract tests for business outcomes vs technical failures."""

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
    FailureErrorCode,
    FAILURE_RETRYABLE,
    GapType,
    GapAlternativeType,
    MessageType,
    ResourceType,
    AllocationRecommendation,
    create_human_evidence,
    create_budget_evidence,
    get_requester_id,
    get_resource_id_1,
)


class FailingHumanLookupRepository(InMemoryResourceRepository):
    async def get_human_resources_by_tenant(self, tenant_id, evaluation_timestamp):
        raise ConnectionError("human lookup unavailable")


class FailingBudgetLookupRepository(InMemoryResourceRepository):
    async def get_budget_resources_by_tenant(self, tenant_id, evaluation_timestamp):
        raise ConnectionError("budget lookup unavailable")


class UnexpectedHumanRepository(InMemoryResourceRepository):
    async def get_human_resources_by_tenant(self, tenant_id, evaluation_timestamp):
        raise ValueError("unexpected internal ranking failure")


def _request_metadata() -> AgentMessageMetadata:
    return AgentMessageMetadata(
        correlation_id=uuid4(),
        process_instance_id=uuid4(),
        task_id=uuid4(),
        tenant_id=get_requester_id(),
        message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
    )


def _available_human(evaluation_timestamp, **overrides):
    return create_human_evidence(
        tenant_id=get_requester_id(),
        reference_timestamp=evaluation_timestamp,
        **overrides,
    )


def _human_request(evaluation_timestamp, **requirement_overrides) -> AllocationRequest:
    base = {
        "resource_type": ResourceType.HUMAN,
        "requester_id": get_requester_id(),
        "task_deadline": evaluation_timestamp + timedelta(days=150),
        "estimated_effort_hours": Decimal("10"),
        "process_stage": "resource_allocation",
    }
    base.update(requirement_overrides)
    return AllocationRequest(
        metadata=_request_metadata(),
        human_requirements=HumanResourceRequirement(**base),
    )


def _budget_request(evaluation_timestamp, **requirement_overrides) -> AllocationRequest:
    base = {
        "resource_type": ResourceType.BUDGET,
        "required_amount": Decimal("5000"),
        "currency": "USD",
        "cost_centre": "CC001",
        "requester_id": get_requester_id(),
        "task_deadline": evaluation_timestamp + timedelta(days=150),
        "process_stage": "resource_allocation",
    }
    base.update(requirement_overrides)
    return AllocationRequest(
        metadata=_request_metadata(),
        budget_requirements=BudgetResourceRequirement(**base),
    )


class TestBusinessOutcomes:
    """Business constraint outcomes must not be technical failures."""

    async def test_eligible_human_returns_pending_human_approval(self, evaluation_timestamp):
        repository = InMemoryResourceRepository()
        repository.add_human_resource(
            _available_human(
                evaluation_timestamp,
                resource_id=get_resource_id_1(),
                roles=["developer"],
                mandatory_skills=["python"],
            )
        )
        service = ResourceAllocationService(repository)

        recommendation = await service.process_allocation_request(
            _human_request(
                evaluation_timestamp,
                required_roles=["developer"],
                mandatory_skills=["python"],
            ),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.PENDING_HUMAN_APPROVAL
        assert recommendation.requires_human_approval is True
        assert recommendation.manual_intervention_required is False
        assert len(recommendation.human_requirement_result.eligible_candidates) == 1

    async def test_no_eligible_human_returns_gap_and_alternatives(self, evaluation_timestamp):
        repository = InMemoryResourceRepository()
        repository.add_human_resource(_available_human(evaluation_timestamp, is_active=False))
        service = ResourceAllocationService(repository)

        recommendation = await service.process_allocation_request(
            _human_request(evaluation_timestamp),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.PENDING_HUMAN_APPROVAL
        assert recommendation.error_code is None
        assert len(recommendation.resource_gaps) == 1
        assert recommendation.resource_gaps[0].gap_type == GapType.NO_ELIGIBLE_HUMAN
        assert len(recommendation.alternatives) == 7
        assert recommendation.alternatives[0].alternative_type == (
            GapAlternativeType.RELAX_NON_MANDATORY_PREFERENCES
        )
        assert all(alt.requires_approval for alt in recommendation.alternatives)

    async def test_missing_evidence_returns_pending_without_ranking(self, evaluation_timestamp):
        repository = InMemoryResourceRepository()
        resource = _available_human(evaluation_timestamp)
        resource.evidence_references = {"source": "partial_fixture"}
        repository.add_human_resource(resource)
        service = ResourceAllocationService(repository)

        recommendation = await service.process_allocation_request(
            _human_request(evaluation_timestamp),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.PENDING_HUMAN_APPROVAL
        assert recommendation.human_requirement_result.eligible_candidates == []
        assert recommendation.resource_gaps[0].gap_type == GapType.MISSING_REQUIRED_EVIDENCE

    async def test_sod_conflicts_return_blocked_allocation_gap(self, evaluation_timestamp):
        repository = InMemoryResourceRepository()
        repository.add_human_resource(_available_human(evaluation_timestamp, sod_conflicts=[uuid4()]))
        service = ResourceAllocationService(repository)

        recommendation = await service.process_allocation_request(
            _human_request(evaluation_timestamp),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.PENDING_HUMAN_APPROVAL
        assert recommendation.resource_gaps[0].gap_type == GapType.SOD_CONFLICT_UNRESOLVED
        assert "segregation-of-duties" in recommendation.explanation.lower()

    async def test_insufficient_budget_returns_pending_with_budget_findings(
        self, evaluation_timestamp
    ):
        repository = InMemoryResourceRepository()
        repository.add_budget_resource(
            create_budget_evidence(
                tenant_id=get_requester_id(),
                reference_timestamp=evaluation_timestamp,
                available_balance=Decimal("100"),
                currency="USD",
                cost_centre="CC001",
            )
        )
        service = ResourceAllocationService(repository)

        recommendation = await service.process_allocation_request(
            _budget_request(evaluation_timestamp, required_amount=Decimal("5000")),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.PENDING_HUMAN_APPROVAL
        assert recommendation.budget_requirement_result.budget_validation.sufficient_balance is False
        assert recommendation.resource_gaps[0].gap_type == GapType.BUDGET_UNAVAILABLE

    async def test_budget_unavailable_no_resource(self, evaluation_timestamp):
        correlation_id = uuid4()
        metadata = AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=get_requester_id(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        request = AllocationRequest(
            metadata=metadata,
            budget_requirements=_budget_request(evaluation_timestamp).budget_requirements,
        )
        service = ResourceAllocationService(InMemoryResourceRepository())

        recommendation = await service.process_allocation_request(
            request,
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.PENDING_HUMAN_APPROVAL
        assert recommendation.status != RecommendationStatus.FAILED
        assert recommendation.requires_human_approval is True
        assert recommendation.manual_intervention_required is False
        assert recommendation.error_code is None
        assert recommendation.budget_requirement_result is not None
        assert recommendation.budget_requirement_result.budget_validation is None
        assert recommendation.budget_requirement_result.eligible_candidates == []
        assert len(recommendation.resource_gaps) == 1
        assert recommendation.resource_gaps[0].gap_type == GapType.BUDGET_UNAVAILABLE
        assert recommendation.explanation.strip()
        assert "budget" in recommendation.explanation.lower()
        assert any("budget" in limitation.lower() for limitation in recommendation.limitations)
        assert recommendation.metadata.correlation_id == correlation_id
        AllocationRecommendation.model_validate(recommendation.model_dump())

    async def test_mixed_human_and_budget_preserves_both_outcomes(self, evaluation_timestamp):
        repository = InMemoryResourceRepository()
        repository.add_human_resource(
            _available_human(
                evaluation_timestamp,
                resource_id=get_resource_id_1(),
                roles=["developer"],
                mandatory_skills=["python"],
            )
        )
        repository.add_budget_resource(
            create_budget_evidence(
                tenant_id=get_requester_id(),
                reference_timestamp=evaluation_timestamp,
                available_balance=Decimal("100"),
                currency="USD",
            )
        )
        service = ResourceAllocationService(repository)

        request = AllocationRequest(
            metadata=_request_metadata(),
            human_requirements=HumanResourceRequirement(
                required_roles=["developer"],
                mandatory_skills=["python"],
                requester_id=get_requester_id(),
                task_deadline=evaluation_timestamp + timedelta(days=150),
                estimated_effort_hours=Decimal("10"),
                process_stage="resource_allocation",
            ),
            budget_requirements=BudgetResourceRequirement(
                required_amount=Decimal("5000"),
                currency="USD",
                requester_id=get_requester_id(),
                task_deadline=evaluation_timestamp + timedelta(days=150),
                process_stage="resource_allocation",
            ),
        )

        recommendation = await service.process_allocation_request(request, evaluation_timestamp)

        assert recommendation.status == RecommendationStatus.PENDING_HUMAN_APPROVAL
        assert len(recommendation.human_requirement_result.eligible_candidates) == 1
        assert recommendation.budget_requirement_result is not None
        assert any(
            gap.gap_type == GapType.BUDGET_UNAVAILABLE
            for gap in recommendation.resource_gaps
        )

    async def test_domain_constraints_do_not_produce_technical_failed(self, evaluation_timestamp):
        repository = InMemoryResourceRepository()
        repository.add_human_resource(_available_human(evaluation_timestamp, is_active=False))
        service = ResourceAllocationService(repository)

        recommendation = await service.process_allocation_request(
            _human_request(evaluation_timestamp),
            evaluation_timestamp,
        )

        assert recommendation.status != RecommendationStatus.FAILED
        assert recommendation.retryable is None


class TestTechnicalFailures:
    """Technical failures must return FAILED without fabricated business results."""

    @pytest.mark.parametrize("error_code", list(FailureErrorCode))
    async def test_failure_codes_define_retryable(self, error_code):
        assert error_code in FAILURE_RETRYABLE

    async def test_invalid_request_empty_requirements(self, evaluation_timestamp):
        service = ResourceAllocationService(InMemoryResourceRepository())
        request = AllocationRequest(
            metadata=_request_metadata(),
            human_requirements=None,
            budget_requirements=None,
        )

        recommendation = await service.process_allocation_request(request, evaluation_timestamp)

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == FailureErrorCode.INVALID_REQUEST.value
        assert recommendation.retryable is False
        assert recommendation.requires_human_approval is False
        assert recommendation.manual_intervention_required is True
        AllocationRecommendation.model_validate(recommendation.model_dump())

    async def test_invalid_request_past_deadline(self, evaluation_timestamp):
        service = ResourceAllocationService(InMemoryResourceRepository())
        recommendation = await service.process_allocation_request(
            _human_request(evaluation_timestamp, task_deadline=evaluation_timestamp - timedelta(days=30)),
            evaluation_timestamp,
        )

        assert recommendation.error_code == FailureErrorCode.INVALID_REQUEST.value

    async def test_repository_exception_returns_resource_lookup_failed(
        self, evaluation_timestamp
    ):
        service = ResourceAllocationService(FailingHumanLookupRepository())
        recommendation = await service.process_allocation_request(
            _human_request(evaluation_timestamp),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == FailureErrorCode.RESOURCE_LOOKUP_FAILED.value
        assert recommendation.retryable is True
        assert "human lookup unavailable" in recommendation.error_message

    async def test_resource_lookup_failed_budget(self, evaluation_timestamp):
        correlation_id = uuid4()
        metadata = AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=get_requester_id(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        request = AllocationRequest(
            metadata=metadata,
            budget_requirements=_budget_request(evaluation_timestamp).budget_requirements,
        )
        service = ResourceAllocationService(FailingBudgetLookupRepository())

        recommendation = await service.process_allocation_request(
            request,
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == FailureErrorCode.RESOURCE_LOOKUP_FAILED.value
        assert recommendation.retryable is True
        assert recommendation.requires_human_approval is False
        assert recommendation.manual_intervention_required is True
        assert recommendation.human_requirement_result is None
        assert recommendation.budget_requirement_result is None
        assert recommendation.resource_gaps == []
        assert recommendation.alternatives == []
        assert recommendation.confidence is None
        assert "budget lookup unavailable" in recommendation.error_message
        assert recommendation.metadata.correlation_id == correlation_id
        AllocationRecommendation.model_validate(recommendation.model_dump())

    async def test_unexpected_exception_returns_internal_error(self, evaluation_timestamp):
        service = ResourceAllocationService(UnexpectedHumanRepository())
        recommendation = await service.process_allocation_request(
            _human_request(evaluation_timestamp),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == FailureErrorCode.INTERNAL_ERROR.value
        assert recommendation.retryable is True
        assert "unexpected internal ranking failure" not in recommendation.error_message

    async def test_failed_output_has_no_ranked_candidates_or_business_payload(
        self, evaluation_timestamp
    ):
        service = ResourceAllocationService(FailingHumanLookupRepository())
        recommendation = await service.process_allocation_request(
            _human_request(evaluation_timestamp),
            evaluation_timestamp,
        )

        assert recommendation.human_requirement_result is None
        assert recommendation.budget_requirement_result is None
        assert recommendation.resource_gaps == []
        assert recommendation.alternatives == []
        assert recommendation.confidence is None

    async def test_correlation_id_preserved_in_failure_path(self, evaluation_timestamp):
        correlation_id = uuid4()
        metadata = AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=get_requester_id(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        request = AllocationRequest(metadata=metadata, human_requirements=None)
        service = ResourceAllocationService(InMemoryResourceRepository())

        recommendation = await service.process_allocation_request(
            request,
            evaluation_timestamp,
        )

        assert recommendation.metadata.correlation_id == correlation_id

    async def test_service_never_raises(self, evaluation_timestamp):
        services = [
            ResourceAllocationService(InMemoryResourceRepository()),
            ResourceAllocationService(FailingHumanLookupRepository()),
            ResourceAllocationService(FailingBudgetLookupRepository()),
            ResourceAllocationService(UnexpectedHumanRepository()),
        ]
        requests = [
            _human_request(evaluation_timestamp),
            _budget_request(evaluation_timestamp),
            AllocationRequest(metadata=_request_metadata()),
        ]

        for service in services:
            for request in requests:
                result = await service.process_allocation_request(request, evaluation_timestamp)
                assert isinstance(result, AllocationRecommendation)
