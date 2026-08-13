"""Deterministic ranking for Agent 3 Resource Allocation."""

from decimal import Decimal, ROUND_HALF_UP
from typing import List
from uuid import UUID

from .schemas import (
    HumanResourceEvidence,
    HumanResourceRequirement,
    RankedHumanCandidate,
    ScoreBreakdown,
)
from .constants import SCORING_WEIGHTS


class HumanResourceRanker:
    """Deterministic ranking of eligible HUMAN resources."""

    def __init__(self):
        """Initialize the ranker."""
        pass

    def rank_candidates(
        self,
        eligible_resources: List[HumanResourceEvidence],
        requirement: HumanResourceRequirement,
    ) -> List[RankedHumanCandidate]:
        """Rank eligible resources using deterministic scoring.
        
        Scoring formula:
        allocation_score = role_match * 0.30
                          + skill_match * 0.25
                          + availability_score * 0.20
                          + workload_fit * 0.15
                          + authority_match * 0.10
        
        Tie-breaking:
        1. Lower projected workload
        2. Earlier availability
        3. Stable resource ID
        """
        scored_candidates = []
        
        for resource in eligible_resources:
            score_breakdown = self._calculate_score_breakdown(resource, requirement)
            scored_candidates.append(
                (resource, score_breakdown, score_breakdown.total_score)
            )
        
        # Sort by total score (descending), then apply deterministic tie-breaking
        scored_candidates.sort(
            key=lambda x: (
                -x[2],  # Higher score first
                x[0].projected_workload_percentage,  # Lower workload first
                x[0].available_from,  # Earlier availability first
                x[0].resource_id,  # Stable resource ID
            )
        )
        
        # Convert to RankedCandidate objects
        ranked_candidates = []
        for rank, (resource, score_breakdown, allocation_score) in enumerate(
            scored_candidates, start=1
        ):
            ranked_candidates.append(
                RankedHumanCandidate(
                    resource_id=resource.resource_id,
                    resource_type=resource.resource_type,
                    name=resource.name,
                    rank=rank,
                    allocation_score=allocation_score,
                    score_breakdown=score_breakdown,
                    current_workload_percentage=resource.current_workload_percentage,
                    projected_workload_percentage=resource.projected_workload_percentage,
                    available_from=resource.available_from,
                    available_until=resource.available_until,
                    evidence_refs=resource.evidence_references,
                )
            )
        
        return ranked_candidates

    def _calculate_score_breakdown(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
    ) -> ScoreBreakdown:
        """Calculate the score breakdown for a resource.
        
        All factors are normalized between 0 and 1.
        """
        role_match = self._calculate_role_match(resource, requirement)
        skill_match = self._calculate_skill_match(resource, requirement)
        availability_score = self._calculate_availability_score(resource, requirement)
        workload_fit = self._calculate_workload_fit(resource, requirement)
        authority_match = self._calculate_authority_match(resource, requirement)
        
        # Calculate total score using exact weights
        total_score = (
            role_match * Decimal(str(SCORING_WEIGHTS["role_match"])) +
            skill_match * Decimal(str(SCORING_WEIGHTS["skill_match"])) +
            availability_score * Decimal(str(SCORING_WEIGHTS["availability_score"])) +
            workload_fit * Decimal(str(SCORING_WEIGHTS["workload_fit"])) +
            authority_match * Decimal(str(SCORING_WEIGHTS["authority_match"]))
        )
        
        # Round to 2 decimal places for stability
        total_score = total_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        return ScoreBreakdown(
            role_match=role_match.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            skill_match=skill_match.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            availability_score=availability_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            workload_fit=workload_fit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            authority_match=authority_match.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            total_score=total_score,
        )

    def _calculate_role_match(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
    ) -> Decimal:
        """Calculate role match score (0-1).
        
        Returns 1.0 if resource has any required role, 0.0 otherwise.
        Note: Mandatory role is already checked in eligibility, so eligible resources
        will have at least one required role. This score reflects the quality of match.
        """
        if not requirement.required_roles:
            return Decimal("1.0")
        
        resource_roles = set(resource.roles)
        required_roles = set(requirement.required_roles)
        
        # If resource has any required role, give full credit
        # (since eligibility already ensures at least one match)
        if resource_roles.intersection(required_roles):
            return Decimal("1.0")
        
        return Decimal("0.0")

    def _calculate_skill_match(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
    ) -> Decimal:
        """Calculate skill match score (0-1).
        
        Includes both mandatory and preferred skills.
        Mandatory skills are already verified in eligibility.
        Preferred skills contribute to the score.
        """
        all_required_skills = set(requirement.mandatory_skills + requirement.preferred_skills)
        
        if not all_required_skills:
            return Decimal("1.0")
        
        resource_skills = set(resource.mandatory_skills + resource.preferred_skills)
        covered_skills = resource_skills.intersection(all_required_skills)
        
        # Ratio of covered skills to total required skills
        skill_match = Decimal(len(covered_skills)) / Decimal(len(all_required_skills))
        
        return skill_match.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calculate_availability_score(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
    ) -> Decimal:
        """Calculate availability score (0-1).
        
        Higher score for resources available sooner.
        """
        if resource.available_from <= requirement.task_deadline:
            # Available before deadline - give full credit
            return Decimal("1.0")
        
        # Not available before deadline (should be excluded by eligibility)
        return Decimal("0.0")

    def _calculate_workload_fit(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
    ) -> Decimal:
        """Calculate workload fit score (0-1).
        
        Higher score for resources with lower projected workload.
        """
        # Invert workload percentage: lower workload = higher score
        workload_fit = (Decimal("100") - resource.projected_workload_percentage) / Decimal("100")
        
        return workload_fit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calculate_authority_match(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
    ) -> Decimal:
        """Calculate authority match score (0-1).
        
        Returns 1.0 if authority matches requirement, 0.0 otherwise.
        Note: Required authority is already checked in eligibility.
        """
        if not requirement.required_authority:
            return Decimal("1.0")
        
        if resource.authority == requirement.required_authority:
            return Decimal("1.0")
        
        return Decimal("0.0")
