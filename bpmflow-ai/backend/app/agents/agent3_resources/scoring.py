"""Explicit, inspectable weighted scoring for Agent 3 HUMAN allocation."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .constants import SCORING_WEIGHTS
from .schemas import (
    HumanResourceEvidence,
    HumanResourceRequirement,
    RankedHumanCandidate,
    ScoreBreakdown,
    WeightedScoreComponent,
)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_role_match(
    resource: HumanResourceEvidence,
    requirement: HumanResourceRequirement,
) -> Decimal:
    """Return 1.0 when the resource holds any required role, else 0.0."""
    if not requirement.required_roles:
        return Decimal("1.0")
    if set(resource.roles).intersection(requirement.required_roles):
        return Decimal("1.0")
    return Decimal("0.0")


def calculate_skill_match(
    resource: HumanResourceEvidence,
    requirement: HumanResourceRequirement,
) -> Decimal:
    """Ratio of covered mandatory + preferred skills to total required skills."""
    all_required_skills = set(requirement.mandatory_skills + requirement.preferred_skills)
    if not all_required_skills:
        return Decimal("1.0")
    resource_skills = set(resource.mandatory_skills + resource.preferred_skills)
    covered = resource_skills.intersection(all_required_skills)
    return _quantize(Decimal(len(covered)) / Decimal(len(all_required_skills)))


def calculate_availability_score(
    resource: HumanResourceEvidence,
    requirement: HumanResourceRequirement,
) -> Decimal:
    """Return 1.0 when available before the task deadline."""
    if resource.available_from <= requirement.task_deadline:
        return Decimal("1.0")
    return Decimal("0.0")


def calculate_workload_fit(resource: HumanResourceEvidence) -> Decimal:
    """Higher score for lower projected workload (inverted percentage)."""
    return _quantize(
        (Decimal("100") - resource.projected_workload_percentage) / Decimal("100")
    )


def calculate_authority_match(
    resource: HumanResourceEvidence,
    requirement: HumanResourceRequirement,
) -> Decimal:
    """Return 1.0 when authority matches requirement, else 0.0."""
    if not requirement.required_authority:
        return Decimal("1.0")
    if resource.authority == requirement.required_authority:
        return Decimal("1.0")
    return Decimal("0.0")


def build_weighted_components(
    role_match: Decimal,
    skill_match: Decimal,
    availability_score: Decimal,
    workload_fit: Decimal,
    authority_match: Decimal,
) -> dict[str, WeightedScoreComponent]:
    """Build named, numeric, explainable weighted score components."""
    raw_scores = {
        "role_match": role_match,
        "skill_match": skill_match,
        "availability_score": availability_score,
        "workload_fit": workload_fit,
        "authority_match": authority_match,
    }
    components: dict[str, WeightedScoreComponent] = {}
    for factor, raw in raw_scores.items():
        weight = Decimal(str(SCORING_WEIGHTS[factor]))
        components[factor] = WeightedScoreComponent(
            factor=factor,
            raw_score=_quantize(raw),
            weight=weight,
            weighted_contribution=_quantize(raw * weight),
        )
    return components


def calculate_score_breakdown(
    resource: HumanResourceEvidence,
    requirement: HumanResourceRequirement,
) -> ScoreBreakdown:
    """Calculate the full weighted score breakdown for one resource."""
    role_match = calculate_role_match(resource, requirement)
    skill_match = calculate_skill_match(resource, requirement)
    availability_score = calculate_availability_score(resource, requirement)
    workload_fit = calculate_workload_fit(resource)
    authority_match = calculate_authority_match(resource, requirement)

    components = build_weighted_components(
        role_match,
        skill_match,
        availability_score,
        workload_fit,
        authority_match,
    )
    total_score = _quantize(
        sum(component.weighted_contribution for component in components.values())
    )

    return ScoreBreakdown(
        role_match=components["role_match"].raw_score,
        skill_match=components["skill_match"].raw_score,
        availability_score=components["availability_score"].raw_score,
        workload_fit=components["workload_fit"].raw_score,
        authority_match=components["authority_match"].raw_score,
        total_score=total_score,
        weighted_components=components,
    )


def rank_human_candidates(
    eligible_resources: list[HumanResourceEvidence],
    requirement: HumanResourceRequirement,
) -> list[RankedHumanCandidate]:
    """Rank eligible HUMAN resources using deterministic weighted scoring."""
    scored: list[tuple[HumanResourceEvidence, ScoreBreakdown, Decimal]] = []
    for resource in eligible_resources:
        breakdown = calculate_score_breakdown(resource, requirement)
        scored.append((resource, breakdown, breakdown.total_score))

    scored.sort(
        key=lambda item: (
            -item[2],
            item[0].projected_workload_percentage,
            item[0].available_from,
            item[0].resource_id,
        )
    )

    ranked: list[RankedHumanCandidate] = []
    for rank, (resource, breakdown, allocation_score) in enumerate(scored, start=1):
        ranked.append(
            RankedHumanCandidate(
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                name=resource.name,
                rank=rank,
                allocation_score=allocation_score,
                score_breakdown=breakdown,
                current_workload_percentage=resource.current_workload_percentage,
                projected_workload_percentage=resource.projected_workload_percentage,
                available_from=resource.available_from,
                available_until=resource.available_until,
                evidence_refs=resource.evidence_references,
            )
        )
    return ranked
