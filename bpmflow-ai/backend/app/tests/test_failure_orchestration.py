"""Contract tests for Agent 3 failure-path orchestration."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

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
    FailureErrorCode,
    FAILURE_RETRYABLE,
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


def _request_metadata() -> AgentMessageMetadata:
    return AgentMessageMetadata(
        correlation_id=uuid4(),
        process_instance_id=uuid4(),
        task_id=uuid4(),
        tenant_id=get_requester_id(),
        message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
    )


def _available_human(**overrides):
    resource = create_human_evidence(tenant_id=get_requester_id(), **overrides)
    resource.available_from = utc_datetime(2025, 12, 1)
    return resource


def _human_request(**requirement_overrides) -> AllocationRequest:
    base = {
        "resource_type": ResourceType.HUMAN,
        "requester_id": get_requester_id(),
        "task_deadline": utc_datetime(2026, 6, 1),
        "estimated_effort_hours": Decimal("10"),
        "process_stage": "resource_allocation",
    }
    base.update(requirement_overrides)
    return AllocationRequest(
        metadata=_request_metadata(),
        human_requirements=HumanResourceRequirement(**base),
    )


def _budget_request(**requirement_overrides) -> AllocationRequest:
    base = {
        "resource_type": ResourceType.BUDGET,
        "required_amount": Decimal("5000"),
        "currency": "USD",
        "cost_centre": "CC001",
        "requester_id": get_requester_id(),
        "task_deadline": utc_datetime(2026, 6, 1),
        "process_stage": "resource_allocation",
    }
    base.update(requirement_overrides)
    return AllocationRequest(
        metadata=_request_metadata(),
        budget_requirements=BudgetResourceRequirement(**base),
    )


class TestFailureOrchestration:
    """Failure-path orchestration contract tests."""

    @pytest.mark.parametrize(
        "error_code",
        list(FailureErrorCode),
    )
    async def test_failure_codes_define_retryable(self, error_code):
        assert error_code in FAILURE_RETRYABLE
        assert isinstance(FAILURE_RETRYABLE[error_code], bool)

    async def test_no_eligible_candidates_failure(self, evaluation_timestamp):
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)
        repository.add_human_resource(
            _available_human(
                resource_id=get_resource_id_1(),
                is_active=False,
            )
        )

        recommendation = await service.process_allocation_request(
            _human_request(),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == FailureErrorCode.NO_ELIGIBLE_CANDIDATES.value
        assert recommendation.retryable is True
        AllocationRecommendation.model_validate(recommendation.model_dump())

    async def test_missing_required_evidence_plan_failure(self, evaluation_timestamp):
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)
        resource = _available_human(resource_id=get_resource_id_1())
        resource.evidence_references = {"source": "partial_fixture"}
        repository.add_human_resource(resource)

        recommendation = await service.process_allocation_request(
            _human_request(),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == FailureErrorCode.MISSING_REQUIRED_EVIDENCE.value
        assert recommendation.retryable is True
        AllocationRecommendation.model_validate(recommendation.model_dump())

    async def test_resource_lookup_failed_human(self, evaluation_timestamp):
        service = ResourceAllocationService(FailingHumanLookupRepository())

        recommendation = await service.process_allocation_request(
            _human_request(),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == FailureErrorCode.RESOURCE_LOOKUP_FAILED.value
        assert recommendation.retryable is True
        assert "human lookup unavailable" in recommendation.error_message
        AllocationRecommendation.model_validate(recommendation.model_dump())

    async def test_resource_lookup_failed_budget(self, evaluation_timestamp):
        repository = FailingBudgetLookupRepository()
        service = ResourceAllocationService(repository)

        recommendation = await service.process_allocation_request(
            _budget_request(),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == FailureErrorCode.RESOURCE_LOOKUP_FAILED.value
        assert recommendation.retryable is True
        AllocationRecommendation.model_validate(recommendation.model_dump())

    async def test_budget_unavailable_no_resource(self, evaluation_timestamp):
        service = ResourceAllocationService(InMemoryResourceRepository())

        recommendation = await service.process_allocation_request(
            _budget_request(),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == FailureErrorCode.BUDGET_UNAVAILABLE.value
        assert recommendation.retryable is True
        AllocationRecommendation.model_validate(recommendation.model_dump())

    async def test_budget_unavailable_validation_failed(self, evaluation_timestamp):
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)
        repository.add_budget_resource(
            create_budget_evidence(
                tenant_id=get_requester_id(),
                available_balance=Decimal("100"),
                currency="USD",
                cost_centre="CC001",
            )
        )

        recommendation = await service.process_allocation_request(
            _budget_request(required_amount=Decimal("5000")),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == FailureErrorCode.BUDGET_UNAVAILABLE.value
        assert recommendation.retryable is True
        AllocationRecommendation.model_validate(recommendation.model_dump())

    async def test_sod_conflict_unresolved_failure(self, evaluation_timestamp):
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)
        repository.add_human_resource(
            _available_human(
                resource_id=get_resource_id_1(),
                sod_conflicts=[uuid4()],
            )
        )

        recommendation = await service.process_allocation_request(
            _human_request(),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == FailureErrorCode.SOD_CONFLICT_UNRESOLVED.value
        assert recommendation.retryable is False
        AllocationRecommendation.model_validate(recommendation.model_dump())

    async def test_invalid_request_empty_requirements(self, evaluation_timestamp):
        service = ResourceAllocationService(InMemoryResourceRepository())
        request = AllocationRequest(
            metadata=_request_metadata(),
            human_requirements=None,
            budget_requirements=None,
        )

        recommendation = await service.process_allocation_request(
            request,
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == FailureErrorCode.INVALID_REQUEST.value
        assert recommendation.retryable is False
        AllocationRecommendation.model_validate(recommendation.model_dump())

    async def test_invalid_request_past_deadline(self, evaluation_timestamp):
        service = ResourceAllocationService(InMemoryResourceRepository())
        request = _human_request(task_deadline=utc_datetime(2025, 1, 1))

        recommendation = await service.process_allocation_request(
            request,
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.error_code == FailureErrorCode.INVALID_REQUEST.value
        assert recommendation.retryable is False
        AllocationRecommendation.model_validate(recommendation.model_dump())

    @pytest.mark.parametrize(
        ("error_code", "retryable"),
        [
            (FailureErrorCode.NO_ELIGIBLE_CANDIDATES, True),
            (FailureErrorCode.MISSING_REQUIRED_EVIDENCE, True),
            (FailureErrorCode.RESOURCE_LOOKUP_FAILED, True),
            (FailureErrorCode.BUDGET_UNAVAILABLE, True),
            (FailureErrorCode.SOD_CONFLICT_UNRESOLVED, False),
            (FailureErrorCode.INVALID_REQUEST, False),
        ],
    )
    async def test_retryable_values(self, error_code, retryable, evaluation_timestamp):
        service = ResourceAllocationService(InMemoryResourceRepository())

        if error_code == FailureErrorCode.NO_ELIGIBLE_CANDIDATES:
            repository = InMemoryResourceRepository()
            repository.add_human_resource(
                _available_human(is_active=False)
            )
            service = ResourceAllocationService(repository)
            request = _human_request()
        elif error_code == FailureErrorCode.MISSING_REQUIRED_EVIDENCE:
            repository = InMemoryResourceRepository()
            resource = _available_human()
            resource.evidence_references = {}
            repository.add_human_resource(resource)
            service = ResourceAllocationService(repository)
            request = _human_request()
        elif error_code == FailureErrorCode.RESOURCE_LOOKUP_FAILED:
            service = ResourceAllocationService(FailingHumanLookupRepository())
            request = _human_request()
        elif error_code == FailureErrorCode.BUDGET_UNAVAILABLE:
            request = _budget_request()
        elif error_code == FailureErrorCode.SOD_CONFLICT_UNRESOLVED:
            repository = InMemoryResourceRepository()
            repository.add_human_resource(
                _available_human(sod_conflicts=[uuid4()])
            )
            service = ResourceAllocationService(repository)
            request = _human_request()
        else:
            request = AllocationRequest(
                metadata=_request_metadata(),
                human_requirements=None,
                budget_requirements=None,
            )

        recommendation = await service.process_allocation_request(
            request,
            evaluation_timestamp,
        )

        assert recommendation.error_code == error_code.value
        assert recommendation.retryable is retryable

    async def test_service_never_raises_for_failure_triggers(self, evaluation_timestamp):
        scenarios = [
            ResourceAllocationService(InMemoryResourceRepository()),
            ResourceAllocationService(FailingHumanLookupRepository()),
        ]
        requests = [
            _human_request(),
            AllocationRequest(metadata=_request_metadata()),
            _budget_request(),
        ]

        for service in scenarios:
            for request in requests:
                recommendation = await service.process_allocation_request(
                    request,
                    evaluation_timestamp,
                )
                assert isinstance(recommendation, AllocationRecommendation)

    async def test_failed_result_does_not_masquerade_as_success(self, evaluation_timestamp):
        repository = InMemoryResourceRepository()
        repository.add_human_resource(_available_human(is_active=False))
        service = ResourceAllocationService(repository)

        recommendation = await service.process_allocation_request(
            _human_request(),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.FAILED
        assert recommendation.human_requirement_result is None
        assert recommendation.budget_requirement_result is None
        assert recommendation.resource_gaps == []
        assert recommendation.alternatives == []
        assert recommendation.confidence is None
        assert not recommendation.explanation.strip()

    async def test_successful_regression_unchanged(self, evaluation_timestamp):
        repository = InMemoryResourceRepository()
        repository.add_human_resource(
            _available_human(
                resource_id=get_resource_id_1(),
                is_active=True,
                roles=["developer"],
                mandatory_skills=["python"],
            )
        )
        service = ResourceAllocationService(repository)

        recommendation = await service.process_allocation_request(
            _human_request(
                required_roles=["developer"],
                mandatory_skills=["python"],
            ),
            evaluation_timestamp,
        )

        assert recommendation.status == RecommendationStatus.PENDING_HUMAN_APPROVAL
        assert recommendation.requires_human_approval is True
        assert recommendation.explanation.strip()
        assert recommendation.confidence is not None
        assert len(recommendation.human_requirement_result.eligible_candidates) > 0
