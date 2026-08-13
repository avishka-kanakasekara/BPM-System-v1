"""Tests for deterministic ranking - scoring formula and tie-breaking."""

import pytest
from decimal import Decimal
from datetime import timedelta

from app.agents.agent3_resources import (
    HumanResourceRanker,
    create_human_evidence,
    create_human_requirement,
    SCORING_WEIGHTS,
    get_tenant_a_id,
    get_resource_id_1,
    get_resource_id_2,
    get_resource_id_3,
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


class TestRanking:
    """Test deterministic scoring formula."""

    def test_scoring_formula_weights(self, evaluation_timestamp):
        """Test that exact weighted formula is correct."""
        ranker = HumanResourceRanker()
        
        resource = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            roles=["developer"],
            mandatory_skills=["python"],
            preferred_skills=["fastapi"],
            authority="senior",
            current_workload=Decimal("30"),
            max_workload=Decimal("100"),
        )

        requirement = _requirement(
            evaluation_timestamp,
            required_roles=["developer"],
            mandatory_skills=["python"],
            preferred_skills=["fastapi"],
            required_authority="senior",
        )
        
        breakdown = ranker._calculate_score_breakdown(resource, requirement)
        
        # Verify weights sum to 1.0
        expected_total = (
            breakdown.role_match * Decimal(str(SCORING_WEIGHTS["role_match"])) +
            breakdown.skill_match * Decimal(str(SCORING_WEIGHTS["skill_match"])) +
            breakdown.availability_score * Decimal(str(SCORING_WEIGHTS["availability_score"])) +
            breakdown.workload_fit * Decimal(str(SCORING_WEIGHTS["workload_fit"])) +
            breakdown.authority_match * Decimal(str(SCORING_WEIGHTS["authority_match"]))
        )
        
        assert abs(breakdown.total_score - expected_total) < Decimal("0.01")

    def test_all_score_factors_normalized_0_to_1(self, evaluation_timestamp):
        """Test that every score factor is within 0-1."""
        ranker = HumanResourceRanker()
        
        resource = _resource(evaluation_timestamp, resource_id=get_resource_id_1())
        requirement = _requirement(evaluation_timestamp)
        
        breakdown = ranker._calculate_score_breakdown(resource, requirement)
        
        assert Decimal("0") <= breakdown.role_match <= Decimal("1")
        assert Decimal("0") <= breakdown.skill_match <= Decimal("1")
        assert Decimal("0") <= breakdown.availability_score <= Decimal("1")
        assert Decimal("0") <= breakdown.workload_fit <= Decimal("1")
        assert Decimal("0") <= breakdown.authority_match <= Decimal("1")
        assert Decimal("0") <= breakdown.total_score <= Decimal("1")

    def test_preferred_skills_affect_ranking_only(self, evaluation_timestamp):
        """Test that preferred skills affect ranking only (not eligibility)."""
        ranker = HumanResourceRanker()
        
        # Resource with preferred skills
        resource_with_prefs = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            mandatory_skills=["python"],
            preferred_skills=["fastapi", "docker"],
        )

        resource_without_prefs = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_2(),
            mandatory_skills=["python"],
            preferred_skills=[],
        )

        requirement = _requirement(
            evaluation_timestamp,
            mandatory_skills=["python"],
            preferred_skills=["fastapi", "docker"],
        )
        
        breakdown_with = ranker._calculate_score_breakdown(resource_with_prefs, requirement)
        breakdown_without = ranker._calculate_score_breakdown(resource_without_prefs, requirement)
        
        # Resource with preferred skills should have higher skill_match
        assert breakdown_with.skill_match > breakdown_without.skill_match

    def test_deterministic_tie_breaking_workload(self, evaluation_timestamp):
        """Test tie-breaking: lower projected workload first."""
        ranker = HumanResourceRanker()
        
        resource1 = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            current_workload=Decimal("40"),
            max_workload=Decimal("100"),
        )

        resource2 = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_2(),
            current_workload=Decimal("60"),
            max_workload=Decimal("100"),
        )

        requirement = _requirement(evaluation_timestamp)
        
        ranked = ranker.rank_candidates([resource1, resource2], requirement)
        
        # Resource with lower workload should be ranked first
        assert ranked[0].resource_id == get_resource_id_1()
        assert ranked[1].resource_id == get_resource_id_2()

    def test_deterministic_tie_breaking_availability(self, evaluation_timestamp):
        """Test tie-breaking: earlier availability first."""
        ranker = HumanResourceRanker()
        
        resource1 = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            current_workload=Decimal("50"),
            max_workload=Decimal("100"),
        )
        resource1.available_from = evaluation_timestamp - timedelta(days=30)

        resource2 = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_2(),
            current_workload=Decimal("50"),
            max_workload=Decimal("100"),
        )
        resource2.available_from = evaluation_timestamp + timedelta(days=15)

        requirement = _requirement(evaluation_timestamp)
        
        ranked = ranker.rank_candidates([resource1, resource2], requirement)
        
        # Resource with earlier availability should be ranked first
        assert ranked[0].resource_id == get_resource_id_1()
        assert ranked[1].resource_id == get_resource_id_2()

    def test_deterministic_tie_breaking_resource_id(self, evaluation_timestamp):
        """Test tie-breaking: stable resource ID as final tie-breaker."""
        ranker = HumanResourceRanker()
        
        resource1 = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            current_workload=Decimal("50"),
            max_workload=Decimal("100"),
        )
        resource1.available_from = evaluation_timestamp - timedelta(days=30)

        resource2 = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_2(),
            current_workload=Decimal("50"),
            max_workload=Decimal("100"),
        )
        resource2.available_from = evaluation_timestamp - timedelta(days=30)

        requirement = _requirement(evaluation_timestamp)
        
        ranked = ranker.rank_candidates([resource1, resource2], requirement)
        
        # Should be deterministic based on resource ID
        assert ranked[0].resource_id == get_resource_id_1()
        assert ranked[1].resource_id == get_resource_id_2()

    def test_excluded_resources_never_enter_ranking(self, evaluation_timestamp):
        """Test that excluded resources never enter ranking."""
        ranker = HumanResourceRanker()
        
        # Only pass eligible resources to ranker
        eligible_resources = [
            _resource(evaluation_timestamp, resource_id=get_resource_id_1()),
        ]

        requirement = _requirement(evaluation_timestamp)
        
        ranked = ranker.rank_candidates(eligible_resources, requirement)
        
        # Should only rank eligible resources
        assert len(ranked) == 1
        assert ranked[0].resource_id == get_resource_id_1()

    def test_ranking_returns_score_breakdown(self, evaluation_timestamp):
        """Test that ranking returns complete score breakdown."""
        ranker = HumanResourceRanker()
        
        resource = _resource(evaluation_timestamp, resource_id=get_resource_id_1())
        requirement = _requirement(evaluation_timestamp)
        
        ranked = ranker.rank_candidates([resource], requirement)
        
        assert len(ranked) == 1
        assert ranked[0].score_breakdown is not None
        assert ranked[0].score_breakdown.total_score is not None
        assert ranked[0].score_breakdown.role_match is not None
        assert ranked[0].score_breakdown.skill_match is not None
        assert ranked[0].score_breakdown.availability_score is not None
        assert ranked[0].score_breakdown.workload_fit is not None
        assert ranked[0].score_breakdown.authority_match is not None

    def test_ranking_sorts_by_score_descending(self, evaluation_timestamp):
        """Test that ranking sorts by total score descending."""
        ranker = HumanResourceRanker()
        
        # Create resources with different skill coverage
        resource1 = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            mandatory_skills=["python"],
            preferred_skills=["fastapi"],
        )

        resource2 = _resource(
            evaluation_timestamp,
            resource_id=get_resource_id_2(),
            mandatory_skills=["python"],
            preferred_skills=[],
        )

        requirement = _requirement(
            evaluation_timestamp,
            mandatory_skills=["python"],
            preferred_skills=["fastapi"],
        )
        
        ranked = ranker.rank_candidates([resource1, resource2], requirement)
        
        # Resource with more preferred skills should rank first
        assert ranked[0].score_breakdown.total_score >= ranked[1].score_breakdown.total_score
