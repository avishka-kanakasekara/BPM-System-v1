"""Tests for eligibility evaluation - all 11 hard exclusion rules."""

from datetime import timedelta
from decimal import Decimal

from app.agents.agent3_resources import (
    EligibilityEvaluator,
    create_human_evidence,
    create_human_requirement,
    ExclusionReason,
    get_tenant_a_id,
    get_requester_id,
    get_resource_id_1,
    get_resource_id_2,
)


def _resource(evaluation_timestamp, **overrides):
    return create_human_evidence(
        tenant_id=get_tenant_a_id(),
        reference_timestamp=evaluation_timestamp,
        **overrides,
    )


def _requirement(evaluation_timestamp, **overrides):
    return create_human_requirement(
        tenant_id=get_tenant_a_id(),
        reference_timestamp=evaluation_timestamp,
        **overrides,
    )


class TestEligibilityRules:
    """Test all 11 hard exclusion rules."""

    def test_inactive_resource_excluded(self, evaluation_timestamp):
        """Test that inactive resources are excluded."""
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            is_active=False,
        )
        requirement = _requirement(evaluation_timestamp)

        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert not is_eligible
        assert any(e.reason == ExclusionReason.INACTIVE_RESOURCE for e in exclusions)

    def test_required_role_missing_excluded(self, evaluation_timestamp):
        """Test that missing required role is excluded."""
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            roles=["tester"],
        )
        requirement = _requirement(
            evaluation_timestamp,
            required_roles=["developer"],
        )

        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert not is_eligible
        assert any(e.reason == ExclusionReason.REQUIRED_ROLE_MISSING for e in exclusions)

    def test_mandatory_skill_missing_excluded(self, evaluation_timestamp):
        """Test that missing mandatory skill is excluded."""
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            mandatory_skills=["javascript"],
        )
        requirement = _requirement(
            evaluation_timestamp,
            mandatory_skills=["python"],
        )

        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert not is_eligible
        assert any(e.reason == ExclusionReason.MANDATORY_SKILL_MISSING for e in exclusions)

    def test_required_authority_missing_excluded(self, evaluation_timestamp):
        """Test that missing required authority is excluded."""
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            authority="junior",
        )
        requirement = _requirement(
            evaluation_timestamp,
            required_authority="senior",
        )

        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert not is_eligible
        assert any(e.reason == ExclusionReason.REQUIRED_AUTHORITY_MISSING for e in exclusions)

    def test_unavailable_before_deadline_excluded(self, evaluation_timestamp):
        """Test that unavailable resources are excluded."""
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            is_active=True,
        )
        resource.available_from = evaluation_timestamp + timedelta(days=60)

        requirement = _requirement(
            evaluation_timestamp,
            deadline_days=30,
        )

        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert not is_eligible
        assert any(e.reason == ExclusionReason.UNAVAILABLE_BEFORE_DEADLINE for e in exclusions)

    def test_projected_workload_exceeded_excluded(self, evaluation_timestamp):
        """Test that projected workload overflow is excluded."""
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            current_workload=Decimal("80"),
            max_workload=Decimal("100"),
        )
        requirement = _requirement(
            evaluation_timestamp,
            estimated_effort=Decimal("40"),
        )

        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert not is_eligible
        assert any(e.reason == ExclusionReason.PROJECTED_WORKLOAD_EXCEEDED for e in exclusions)

    def test_sod_violation_excluded(self, evaluation_timestamp):
        """Test that segregation of duties violations are excluded."""
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            sod_conflicts=[get_resource_id_2()],
        )
        requirement = _requirement(evaluation_timestamp)

        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert not is_eligible
        assert any(e.reason == ExclusionReason.SEGREGATION_OF_DUTIES_VIOLATION for e in exclusions)

    def test_requester_self_approval_excluded(self, evaluation_timestamp):
        """Test that requester self-approval is excluded."""
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = _resource(
            evaluation_timestamp,
            resource_id=get_requester_id(),
        )
        requirement = _requirement(
            evaluation_timestamp,
            requester_id=get_requester_id(),
        )

        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert not is_eligible
        assert any(e.reason == ExclusionReason.REQUESTER_SELF_APPROVAL for e in exclusions)

    def test_conflict_of_interest_excluded(self, evaluation_timestamp):
        """Test that conflict of interest flags are excluded."""
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            coi_flags=["vendor_relationship"],
        )
        requirement = _requirement(evaluation_timestamp)

        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert not is_eligible
        assert any(e.reason == ExclusionReason.CONFLICT_OF_INTEREST for e in exclusions)

    def test_missing_evidence_excluded(self, evaluation_timestamp):
        """Test that missing required evidence is excluded."""
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
        )
        resource.evidence_references = {}

        requirement = _requirement(evaluation_timestamp)

        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert not is_eligible
        assert any(e.reason == ExclusionReason.MISSING_REQUIRED_EVIDENCE for e in exclusions)

    def test_stale_evidence_excluded(self, evaluation_timestamp):
        """Test that stale evidence is excluded."""
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            evidence_age_days=100,
        )
        requirement = _requirement(evaluation_timestamp)

        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert not is_eligible
        assert any(e.reason == ExclusionReason.STALE_EVIDENCE for e in exclusions)

    def test_multiple_exclusion_reasons_collected(self, evaluation_timestamp):
        """Test that multiple exclusion reasons are collected for one resource."""
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            is_active=False,
            roles=["wrong_role"],
            evidence_age_days=100,
        )
        requirement = _requirement(
            evaluation_timestamp,
            required_roles=["developer"],
        )

        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert not is_eligible
        assert len(exclusions) >= 2
        reasons = [e.reason for e in exclusions]
        assert ExclusionReason.INACTIVE_RESOURCE in reasons
        assert ExclusionReason.REQUIRED_ROLE_MISSING in reasons

    def test_eligible_resource_passes_all_checks(self, evaluation_timestamp):
        """Test that a fully eligible resource passes all checks."""
        evaluator = EligibilityEvaluator(evaluation_timestamp)

        resource = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            is_active=True,
            roles=["developer"],
            mandatory_skills=["python"],
            authority="senior",
            current_workload=Decimal("30"),
            max_workload=Decimal("100"),
            evidence_age_days=30,
        )
        requirement = _requirement(
            evaluation_timestamp,
            required_roles=["developer"],
            mandatory_skills=["python"],
            required_authority="senior",
            estimated_effort=Decimal("10"),
        )

        is_eligible, exclusions = evaluator.evaluate_eligibility(resource, requirement)

        assert is_eligible
        assert len(exclusions) == 0
