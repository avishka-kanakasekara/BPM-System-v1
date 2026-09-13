"""G3 exit tests — demo tenant allocation, advisory-only, cross-tenant isolation."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

pytestmark = pytest.mark.anyio

from app.agents.agent3_resources.advisory import (
    AdvisoryViolationError,
    assert_advisory_recommendation,
)
from app.agents.agent3_resources.application_service import PersistentResourceAllocationService
from app.agents.agent3_resources.constants import (
    ExclusionReason,
    MessageType,
    RecommendationStatus,
    ResourceType,
)
from app.agents.agent3_resources.demo_tenant import build_demo_tenant_repository
from app.agents.agent3_resources.explainer_template import ExplanationContext, TemplateExplainer
from app.agents.agent3_resources.repositories.seed_constants import (
    AGENT3_DEMO_TENANT_ID,
    AGENT3_OTHER_TENANT_ID,
    BUDGET_VALID_ID,
    DEMO_REQUESTER_ID,
    HUMAN_ELIGIBLE_ID,
    HUMAN_SOD_CONFLICT_ID,
    SEED_EVALUATION_TIMESTAMP,
)
from app.agents.agent3_resources.schemas import (
    AgentMessageMetadata,
    AllocationRequest,
    BudgetResourceRequirement,
    HumanResourceRequirement,
)
from app.agents.agent3_resources.service import ResourceAllocationService
from app.tests.test_application_service import FakePersistence


class SilentExplainer:
    """Explanation generator that must not influence ranking."""

    async def generate_explanation(self, context: ExplanationContext) -> str:
        return "Advisory recommendation — human approval required."


def _g3_request(**overrides) -> AllocationRequest:
    correlation_id = overrides.pop("correlation_id", uuid4())
    metadata = AgentMessageMetadata(
        correlation_id=correlation_id,
        process_instance_id=uuid4(),
        task_id=uuid4(),
        tenant_id=AGENT3_DEMO_TENANT_ID,
        message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        timestamp=SEED_EVALUATION_TIMESTAMP,
    )
    human_req = HumanResourceRequirement(
        resource_type=ResourceType.HUMAN,
        required_roles=["developer"],
        mandatory_skills=["python"],
        preferred_skills=["fastapi"],
        required_authority="senior",
        requester_id=DEMO_REQUESTER_ID,
        task_deadline=SEED_EVALUATION_TIMESTAMP + timedelta(days=150),
        estimated_effort_hours=Decimal("5"),
        process_stage="resource_allocation",
    )
    budget_req = BudgetResourceRequirement(
        resource_type=ResourceType.BUDGET,
        required_amount=Decimal("10000"),
        currency="USD",
        cost_centre="CC-DEMO",
        requester_id=DEMO_REQUESTER_ID,
        task_deadline=SEED_EVALUATION_TIMESTAMP + timedelta(days=150),
        process_stage="resource_allocation",
    )
    return AllocationRequest(
        metadata=metadata,
        human_requirements=human_req,
        budget_requirements=budget_req,
    )


class TestAgent3G3Exit:
    async def test_g3_demo_tenant_produces_three_plus_candidates(self):
        repository = build_demo_tenant_repository()
        service = ResourceAllocationService(repository, explainer=SilentExplainer())
        recommendation = await service.process_allocation_request(
            _g3_request(),
            evaluation_timestamp=SEED_EVALUATION_TIMESTAMP,
        )

        human_result = recommendation.human_requirement_result
        assert human_result is not None
        assert len(human_result.eligible_candidates) >= 3
        assert human_result.eligible_candidates[0].rank == 1
        top = human_result.eligible_candidates[0]
        assert top.score_breakdown.weighted_components
        assert "role_match" in top.score_breakdown.weighted_components

    async def test_g3_sod_conflict_is_excluded_with_reason(self):
        repository = build_demo_tenant_repository()
        service = ResourceAllocationService(repository, explainer=SilentExplainer())
        recommendation = await service.process_allocation_request(
            _g3_request(),
            evaluation_timestamp=SEED_EVALUATION_TIMESTAMP,
        )

        excluded_ids = {
            item.resource_id
            for item in recommendation.human_requirement_result.excluded_resources
        }
        assert HUMAN_SOD_CONFLICT_ID in excluded_ids
        sod_entry = next(
            item
            for item in recommendation.human_requirement_result.excluded_resources
            if item.resource_id == HUMAN_SOD_CONFLICT_ID
        )
        reasons = {entry.reason for entry in sod_entry.exclusion_reasons}
        assert ExclusionReason.SEGREGATION_OF_DUTIES_VIOLATION in reasons

    async def test_g3_budget_validation_present(self):
        repository = build_demo_tenant_repository()
        service = ResourceAllocationService(repository, explainer=SilentExplainer())
        recommendation = await service.process_allocation_request(
            _g3_request(),
            evaluation_timestamp=SEED_EVALUATION_TIMESTAMP,
        )

        budget_result = recommendation.budget_requirement_result
        assert budget_result is not None
        validation = budget_result.budget_validation
        assert validation is not None
        assert validation.resource_id == BUDGET_VALID_ID
        assert validation.sufficient_balance is True
        assert validation.cost_centre_match is True
        assert validation.currency_match is True
        assert validation.within_authorization_limit is True

    async def test_g3_ranking_unchanged_when_explainer_disabled(self):
        repository = build_demo_tenant_repository()
        request = _g3_request()

        with_template = ResourceAllocationService(
            repository,
            explainer=TemplateExplainer(),
        )
        with_silent = ResourceAllocationService(
            repository,
            explainer=SilentExplainer(),
        )

        rec_template = await with_template.process_allocation_request(
            request,
            evaluation_timestamp=SEED_EVALUATION_TIMESTAMP,
        )
        rec_silent = await with_silent.process_allocation_request(
            request,
            evaluation_timestamp=SEED_EVALUATION_TIMESTAMP,
        )

        template_ranking = [
            (candidate.resource_id, candidate.allocation_score)
            for candidate in rec_template.human_requirement_result.eligible_candidates
        ]
        silent_ranking = [
            (candidate.resource_id, candidate.allocation_score)
            for candidate in rec_silent.human_requirement_result.eligible_candidates
        ]
        assert template_ranking == silent_ranking
        assert rec_template.explanation != rec_silent.explanation

    async def test_g3_advisory_only_enforced_in_code(self):
        repository = build_demo_tenant_repository()
        service = ResourceAllocationService(repository, explainer=SilentExplainer())
        recommendation = await service.process_allocation_request(
            _g3_request(),
            evaluation_timestamp=SEED_EVALUATION_TIMESTAMP,
        )

        assert recommendation.requires_human_approval is True
        assert recommendation.status == RecommendationStatus.PENDING_HUMAN_APPROVAL
        assert_advisory_recommendation(recommendation)

        invalid = recommendation.model_copy(update={"requires_human_approval": False})
        with pytest.raises(AdvisoryViolationError):
            assert_advisory_recommendation(invalid)

    async def test_g3_cross_tenant_resources_invisible(self):
        repository = build_demo_tenant_repository(include_other_tenant=True)
        humans = await repository.get_human_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        other_humans = await repository.get_human_resources_by_tenant(
            AGENT3_OTHER_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        demo_ids = {item.resource_id for item in humans}
        other_ids = {item.resource_id for item in other_humans}
        assert HUMAN_ELIGIBLE_ID in demo_ids
        assert demo_ids.isdisjoint(other_ids)

    async def test_g3_persist_and_retrieve_by_correlation_id(self):
        repository = build_demo_tenant_repository()
        allocation_service = ResourceAllocationService(repository, explainer=SilentExplainer())
        recommendation_id = uuid4()
        fake_persistence = FakePersistence(recommendation_id)

        app_service = PersistentResourceAllocationService(
            allocation_service=allocation_service,
            persistence=fake_persistence,
        )
        request = _g3_request()
        result = await app_service.process_and_persist(
            request,
            evaluation_timestamp=SEED_EVALUATION_TIMESTAMP,
        )

        assert result.persisted is True
        assert result.correlation_id == request.metadata.correlation_id
        assert result.recommendation_id == recommendation_id
        assert fake_persistence.last_recommendation.requires_human_approval is True
        assert len(
            fake_persistence.last_recommendation.human_requirement_result.eligible_candidates
        ) >= 3
