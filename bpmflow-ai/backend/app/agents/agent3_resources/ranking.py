"""Deterministic ranking for Agent 3 Resource Allocation."""


from .schemas import (
    HumanResourceEvidence,
    HumanResourceRequirement,
    RankedHumanCandidate,
    ScoreBreakdown,
)
from .scoring import calculate_score_breakdown, rank_human_candidates


class HumanResourceRanker:
    """Deterministic ranking of eligible HUMAN resources."""

    def rank_candidates(
        self,
        eligible_resources: list[HumanResourceEvidence],
        requirement: HumanResourceRequirement,
    ) -> list[RankedHumanCandidate]:
        """Rank eligible resources using explicit weighted scoring."""
        return rank_human_candidates(eligible_resources, requirement)

    def _calculate_score_breakdown(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
    ) -> ScoreBreakdown:
        """Calculate the score breakdown for a resource."""
        return calculate_score_breakdown(resource, requirement)
