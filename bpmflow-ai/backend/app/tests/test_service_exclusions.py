"""Tests for multiple exclusion reasons per resource."""

import pytest
from uuid import uuid4
from decimal import Decimal

pytestmark = pytest.mark.anyio

from app.tests.conftest import utc_datetime

from app.agents.agent3_resources import (
    HumanResourceStrategy,
    InMemoryResourceRepository,
    HumanResourceRequirement,
    MessageType,
    ResourceType,
    ExclusionReason,
    create_human_evidence,
    get_requester_id,
    get_resource_id_1,
    get_tenant_a_id,
    get_tenant_b_id,
)


class TestServiceExclusions:
    """Test exclusion behavior at the HUMAN strategy layer."""

    async def test_multiple_exclusion_reasons_collected(self, evaluation_timestamp):
        """Test that multiple exclusion reasons are collected for one resource."""
        repository = InMemoryResourceRepository()
        strategy = HumanResourceStrategy(repository)

        resource = create_human_evidence(
            tenant_id=get_requester_id(),
            resource_id=get_resource_id_1(),
            is_active=False,
            roles=["wrong_role"],
            evidence_age_days=100,
        )
        resource.available_from = utc_datetime(2025, 12, 1)
        repository.add_human_resource(resource)

        requirement = HumanResourceRequirement(
            resource_type=ResourceType.HUMAN,
            required_roles=["developer"],
            requester_id=get_requester_id(),
            task_deadline=utc_datetime(2026, 6, 1),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )

        result = await strategy.process_requirement(requirement, evaluation_timestamp)

        excluded = result.excluded_resources
        assert len(excluded) == 1

        reasons = excluded[0].exclusion_reasons
        reason_types = [r.reason for r in reasons]

        assert len(reasons) >= 2
        assert ExclusionReason.INACTIVE_RESOURCE in reason_types
        assert ExclusionReason.REQUIRED_ROLE_MISSING in reason_types

    async def test_excluded_resources_never_enter_ranking(self, evaluation_timestamp):
        """Test that excluded resources never enter ranking."""
        repository = InMemoryResourceRepository()
        strategy = HumanResourceStrategy(repository)

        repository.add_human_resource(
            create_human_evidence(
                tenant_id=get_requester_id(),
                resource_id=get_resource_id_1(),
                is_active=False,
            )
        )

        requirement = HumanResourceRequirement(
            resource_type=ResourceType.HUMAN,
            requester_id=get_requester_id(),
            task_deadline=utc_datetime(2026, 6, 1),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )

        result = await strategy.process_requirement(requirement, evaluation_timestamp)

        assert len(result.eligible_candidates) == 0
        assert len(result.excluded_resources) > 0

    async def test_cross_tenant_resources_invisible(self, evaluation_timestamp):
        """Test that cross-tenant resources are invisible."""
        repository = InMemoryResourceRepository()
        strategy = HumanResourceStrategy(repository)

        repository.add_human_resource(
            create_human_evidence(
                tenant_id=get_tenant_b_id(),
                resource_id=get_resource_id_1(),
                is_active=True,
                roles=["developer"],
                mandatory_skills=["python"],
            )
        )

        requirement = HumanResourceRequirement(
            resource_type=ResourceType.HUMAN,
            required_roles=["developer"],
            mandatory_skills=["python"],
            requester_id=get_requester_id(),
            task_deadline=utc_datetime(2026, 6, 1),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )

        result = await strategy.process_requirement(requirement, evaluation_timestamp)

        assert len(result.eligible_candidates) == 0
        assert len(result.excluded_resources) == 0
