"""Tests for Agent 3 schema validation and message contract."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from pydantic import ValidationError

from app.tests.conftest import utc_datetime
from app.agents.agent3_resources import (
    AgentMessageMetadata,
    HumanResourceRequirement,
    BudgetResourceRequirement,
    AllocationRequest,
    AllocationRecommendation,
    RecommendationStatus,
    MessageType,
    ResourceType,
    RequirementResult,
    RankedHumanCandidate,
    ScoreBreakdown,
    BudgetValidationResult,
    ResourceAllocationService,
    InMemoryResourceRepository,
    EligibilityEvaluator,
    ExclusionReason,
    create_human_evidence,
    create_human_requirement,
    utc_now,
    validate_timezone_aware,
    SCHEMA_VERSION,
    AGENT_3_SENDER,
    AGENT_4_RECEIVER,
)


def _metadata(**overrides):
    base = {
        "correlation_id": uuid4(),
        "process_instance_id": uuid4(),
        "task_id": uuid4(),
        "tenant_id": uuid4(),
        "message_type": MessageType.RESOURCE_ALLOCATION_RESPONSE,
    }
    base.update(overrides)
    return AgentMessageMetadata(**base)


def _successful_recommendation_kwargs(**overrides):
    base = {
        "status": RecommendationStatus.PENDING_HUMAN_APPROVAL,
        "requires_human_approval": True,
        "explanation": "Evidence-based recommendation",
        "confidence": Decimal("0.80"),
        "human_requirement_result": None,
        "budget_requirement_result": None,
        "resource_gaps": [],
        "alternatives": [],
        "limitations": [],
    }
    base.update(overrides)
    return base


def _sample_ranked_candidate(**overrides):
    base = {
        "resource_id": uuid4(),
        "name": "Test Employee",
        "rank": 1,
        "allocation_score": Decimal("0.93"),
        "score_breakdown": ScoreBreakdown(
            role_match=Decimal("1.0"),
            skill_match=Decimal("1.0"),
            availability_score=Decimal("1.0"),
            workload_fit=Decimal("0.50"),
            authority_match=Decimal("1.0"),
            total_score=Decimal("0.93"),
        ),
        "current_workload_percentage": Decimal("50"),
        "projected_workload_percentage": Decimal("60"),
        "available_from": utc_datetime(2026, 1, 1),
        "evidence_refs": {"availability": {}, "workload": {}},
    }
    base.update(overrides)
    return RankedHumanCandidate(**base)


class TestAgent3Contract:
    """Test Agent 3 message contract and schema validation."""

    def test_agent_message_metadata_required_fields(self):
        correlation_id = uuid4()
        process_instance_id = uuid4()
        task_id = uuid4()
        tenant_id = uuid4()

        metadata = AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=process_instance_id,
            task_id=task_id,
            tenant_id=tenant_id,
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )

        assert metadata.message_id is not None
        assert metadata.schema_version == SCHEMA_VERSION
        assert metadata.correlation_id == correlation_id
        assert metadata.sender == AGENT_3_SENDER
        assert metadata.receiver == AGENT_4_RECEIVER
        assert metadata.timestamp.tzinfo is not None

    @pytest.mark.anyio
    async def test_service_generated_datetimes_are_timezone_aware(self, evaluation_timestamp):
        repository = InMemoryResourceRepository()
        service = ResourceAllocationService(repository)

        request = AllocationRequest(
            metadata=AgentMessageMetadata(
                correlation_id=uuid4(),
                process_instance_id=uuid4(),
                task_id=uuid4(),
                tenant_id=uuid4(),
                message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            ),
            human_requirements=create_human_requirement(tenant_id=uuid4()),
        )

        recommendation = await service.process_allocation_request(request, evaluation_timestamp)

        assert recommendation.metadata.timestamp.tzinfo is not None
        validate_timezone_aware(recommendation.metadata.timestamp, "metadata.timestamp")

    def test_naive_and_aware_datetimes_are_not_mixed(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            HumanResourceRequirement(
                requester_id=uuid4(),
                task_deadline=datetime(2026, 6, 1),
                estimated_effort_hours=Decimal("10"),
                process_stage="resource_allocation",
            )

        with pytest.raises(ValueError, match="timezone-aware"):
            validate_timezone_aware(datetime(2026, 1, 1), "evaluation_timestamp")

    def test_successful_recommendation_requires_non_empty_explanation(self):
        with pytest.raises(ValidationError, match="non-empty explanation"):
            AllocationRecommendation(
                metadata=_metadata(),
                **_successful_recommendation_kwargs(explanation=""),
            )

    def test_successful_recommendation_requires_confidence(self):
        with pytest.raises(ValidationError, match="requires confidence"):
            AllocationRecommendation(
                metadata=_metadata(),
                **_successful_recommendation_kwargs(confidence=None),
            )

    def test_confidence_outside_range_rejected(self):
        with pytest.raises(ValidationError):
            AllocationRecommendation(
                metadata=_metadata(),
                **_successful_recommendation_kwargs(confidence=Decimal("-0.1")),
            )
        with pytest.raises(ValidationError):
            AllocationRecommendation(
                metadata=_metadata(),
                **_successful_recommendation_kwargs(confidence=Decimal("1.1")),
            )

    def test_pending_human_approval_always_requires_human_approval(self):
        with pytest.raises(ValueError, match="Agent 3 must always require human approval"):
            AllocationRecommendation(
                metadata=_metadata(),
                **_successful_recommendation_kwargs(requires_human_approval=False),
            )

    def test_failed_output_cannot_masquerade_as_valid_recommendation(self):
        with pytest.raises(ValidationError, match="requires error_code"):
            AllocationRecommendation(
                metadata=_metadata(),
                status=RecommendationStatus.FAILED,
                requires_human_approval=True,
                explanation="Should not satisfy FAILED contract alone",
                confidence=Decimal("0.5"),
            )

        failed = AllocationRecommendation(
            metadata=_metadata(),
            status=RecommendationStatus.FAILED,
            requires_human_approval=True,
            explanation="",
            error_code="PIPELINE_ERROR",
            error_message="Allocation pipeline failed",
            retryable=True,
        )
        assert failed.status == RecommendationStatus.FAILED
        assert failed.error_code == "PIPELINE_ERROR"

    def test_ranked_human_candidate_requires_available_from(self):
        with pytest.raises(ValidationError):
            RankedHumanCandidate(
                resource_id=uuid4(),
                name="Missing availability",
                rank=1,
                allocation_score=Decimal("0.85"),
                score_breakdown=ScoreBreakdown(
                    role_match=Decimal("1.0"),
                    skill_match=Decimal("1.0"),
                    availability_score=Decimal("1.0"),
                    workload_fit=Decimal("0.5"),
                    authority_match=Decimal("1.0"),
                    total_score=Decimal("0.85"),
                ),
                current_workload_percentage=Decimal("50"),
                projected_workload_percentage=Decimal("60"),
                evidence_refs={"availability": {}, "workload": {}},
            )

    def test_ranked_human_candidate_requires_workload_data(self):
        with pytest.raises(ValidationError):
            RankedHumanCandidate(
                resource_id=uuid4(),
                name="Missing workload",
                rank=1,
                allocation_score=Decimal("0.85"),
                score_breakdown=ScoreBreakdown(
                    role_match=Decimal("1.0"),
                    skill_match=Decimal("1.0"),
                    availability_score=Decimal("1.0"),
                    workload_fit=Decimal("0.5"),
                    authority_match=Decimal("1.0"),
                    total_score=Decimal("0.85"),
                ),
                available_from=utc_datetime(2026, 1, 1),
                evidence_refs={"availability": {}, "workload": {}},
            )

    def test_missing_availability_or_workload_evidence_results_in_exclusion(
        self, evaluation_timestamp
    ):
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = create_human_evidence(
            tenant_id=uuid4(),
        )
        resource.evidence_references = {"source": "partial_fixture"}

        requirement = create_human_requirement(tenant_id=uuid4())
        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert not is_eligible
        assert any(
            e.reason == ExclusionReason.MISSING_REQUIRED_EVIDENCE for e in exclusions
        )

    def test_budget_result_does_not_require_human_availability_fields(self):
        budget_result = RequirementResult(
            resource_type=ResourceType.BUDGET,
            budget_validation=BudgetValidationResult(
                resource_id=uuid4(),
                name="Team Budget",
                sufficient_balance=True,
                cost_centre_match=True,
                currency_match=True,
                validity_period_valid=True,
                within_authorization_limit=True,
                available_balance=Decimal("10000"),
                required_amount=Decimal("5000"),
            ),
        )

        assert budget_result.eligible_candidates == []
        assert budget_result.budget_validation is not None

    def test_agent3_never_emits_approved_or_rejected(self):
        with pytest.raises(ValidationError):
            AllocationRecommendation(
                metadata=_metadata(),
                **_successful_recommendation_kwargs(status="APPROVED"),  # type: ignore[arg-type]
            )
        with pytest.raises(ValidationError):
            AllocationRecommendation(
                metadata=_metadata(),
                **_successful_recommendation_kwargs(status="REJECTED"),  # type: ignore[arg-type]
            )

    def test_human_resource_requirement_validation(self):
        requirement = HumanResourceRequirement(
            resource_type=ResourceType.HUMAN,
            required_roles=["developer"],
            mandatory_skills=["python"],
            preferred_skills=["fastapi"],
            required_authority="senior",
            requester_id=uuid4(),
            task_deadline=utc_datetime(2026, 6, 1),
            estimated_effort_hours=Decimal("40"),
            process_stage="resource_allocation",
        )

        assert requirement.resource_type == ResourceType.HUMAN
        assert requirement.task_deadline.tzinfo is not None

    def test_budget_resource_requirement_validation(self):
        requirement = BudgetResourceRequirement(
            resource_type=ResourceType.BUDGET,
            required_amount=Decimal("5000"),
            currency="USD",
            cost_centre="CC001",
            requester_id=uuid4(),
            task_deadline=utc_datetime(2026, 6, 1),
            process_stage="resource_allocation",
        )

        assert requirement.resource_type == ResourceType.BUDGET

    def test_allocation_request_validation(self):
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )

        request = AllocationRequest(
            metadata=metadata,
            human_requirements=HumanResourceRequirement(
                requester_id=uuid4(),
                task_deadline=utc_datetime(2026, 6, 1),
                estimated_effort_hours=Decimal("40"),
                process_stage="resource_allocation",
            ),
            budget_requirements=BudgetResourceRequirement(
                required_amount=Decimal("5000"),
                currency="USD",
                requester_id=uuid4(),
                task_deadline=utc_datetime(2026, 6, 1),
                process_stage="resource_allocation",
            ),
        )

        assert request.metadata == metadata

    def test_successful_statuses_require_complete_contract(self):
        for status in (
            RecommendationStatus.GENERATED,
            RecommendationStatus.PENDING_HUMAN_APPROVAL,
            RecommendationStatus.SUPERSEDED,
        ):
            recommendation = AllocationRecommendation(
                metadata=_metadata(),
                **_successful_recommendation_kwargs(status=status),
            )
            assert recommendation.explanation.strip()
            assert recommendation.confidence is not None
            assert recommendation.requires_human_approval is True

    def test_ranked_human_candidate_contract_fields(self):
        candidate = _sample_ranked_candidate()
        assert candidate.rank == 1
        assert candidate.allocation_score == candidate.score_breakdown.total_score
        assert candidate.available_from.tzinfo is not None
        assert candidate.evidence_refs

    def test_utc_now_is_timezone_aware(self):
        now = utc_now()
        assert now.tzinfo == timezone.utc

    def test_correlation_id_preservation(self):
        correlation_id = uuid4()

        request_metadata = AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )

        response_metadata = AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=request_metadata.process_instance_id,
            task_id=request_metadata.task_id,
            tenant_id=request_metadata.tenant_id,
            message_type=MessageType.RESOURCE_ALLOCATION_RESPONSE,
        )

        assert response_metadata.correlation_id == correlation_id
