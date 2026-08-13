"""Resource gap detection and alternatives for Agent 3."""

from typing import List, Optional, Tuple

from decimal import Decimal

from .schemas import (
    RequirementResult,
    ResourceGap,
    ResourceAlternative,
)
from .constants import ResourceType, GapAlternativeType, GapType, ExclusionReason


def _all_have_exclusion_reason(excluded_resources, reason: ExclusionReason) -> bool:
    if not excluded_resources:
        return False
    return all(
        any(entry.reason == reason for entry in resource.exclusion_reasons)
        for resource in excluded_resources
    )


def _any_have_exclusion_reason(excluded_resources, reason: ExclusionReason) -> bool:
    return any(
        any(entry.reason == reason for entry in resource.exclusion_reasons)
        for resource in excluded_resources
    )


class GapDetector:
    """Detects business constraint gaps and generates ordered alternatives."""

    def analyze_human_constraint(
        self,
        requirement_result: RequirementResult,
    ) -> Tuple[List[ResourceGap], List[ResourceAlternative], List[str]]:
        """Analyze a completed HUMAN requirement for business constraint gaps."""
        gaps: List[ResourceGap] = []
        alternatives: List[ResourceAlternative] = []
        limitations: List[str] = []

        if not requirement_result or requirement_result.eligible_candidates:
            return gaps, alternatives, limitations

        excluded = requirement_result.excluded_resources
        eligible_count = len(requirement_result.eligible_candidates)
        excluded_count = len(excluded)

        if _all_have_exclusion_reason(excluded, ExclusionReason.MISSING_REQUIRED_EVIDENCE):
            gaps.append(
                ResourceGap(
                    gap_type=GapType.MISSING_REQUIRED_EVIDENCE,
                    resource_type=ResourceType.HUMAN,
                    gap_description=(
                        "Required availability or workload evidence is missing for all "
                        "candidates; ranking cannot proceed safely"
                    ),
                    eligible_count=eligible_count,
                    excluded_count=excluded_count,
                )
            )
            limitations.append(
                "Recommend clarification or manual evidence verification before allocation"
            )
            return gaps, alternatives, limitations

        if _all_have_exclusion_reason(
            excluded,
            ExclusionReason.SEGREGATION_OF_DUTIES_VIOLATION,
        ):
            gaps.append(
                ResourceGap(
                    gap_type=GapType.SOD_CONFLICT_UNRESOLVED,
                    resource_type=ResourceType.HUMAN,
                    gap_description=(
                        "Allocation is blocked by segregation-of-duties conflicts "
                        "with no alternative candidate available"
                    ),
                    eligible_count=eligible_count,
                    excluded_count=excluded_count,
                )
            )
            limitations.append(
                "Escalate to Agent 4 or human review to resolve segregation-of-duties conflicts"
            )
            return gaps, alternatives, limitations

        if _any_have_exclusion_reason(
            excluded,
            ExclusionReason.PROJECTED_WORKLOAD_EXCEEDED,
        ):
            gaps.append(
                ResourceGap(
                    gap_type=GapType.WORKLOAD_CAPACITY,
                    resource_type=ResourceType.HUMAN,
                    gap_description="No candidate has sufficient workload capacity for this task",
                    eligible_count=eligible_count,
                    excluded_count=excluded_count,
                )
            )
            alternatives = self.generate_alternatives(ResourceType.HUMAN)
            limitations.append("Workload capacity gap detected for all evaluated candidates")
            return gaps, alternatives, limitations

        if _any_have_exclusion_reason(
            excluded,
            ExclusionReason.UNAVAILABLE_BEFORE_DEADLINE,
        ):
            gaps.append(
                ResourceGap(
                    gap_type=GapType.UNAVAILABLE_RESOURCES,
                    resource_type=ResourceType.HUMAN,
                    gap_description="No candidate is available before the task deadline",
                    eligible_count=eligible_count,
                    excluded_count=excluded_count,
                )
            )
            alternatives = self.generate_alternatives(ResourceType.HUMAN)
            limitations.append("Resource availability gap detected for all evaluated candidates")
            return gaps, alternatives, limitations

        gaps.append(
            ResourceGap(
                gap_type=GapType.NO_ELIGIBLE_HUMAN,
                resource_type=ResourceType.HUMAN,
                gap_description="No eligible HUMAN resources found for this requirement",
                eligible_count=eligible_count,
                excluded_count=excluded_count,
            )
        )
        alternatives = self.generate_alternatives(ResourceType.HUMAN)
        limitations.append("No eligible HUMAN resources found for this requirement")
        return gaps, alternatives, limitations

    def analyze_budget_constraint(
        self,
        requirement_result: RequirementResult,
    ) -> Tuple[List[ResourceGap], List[str]]:
        """Analyze a completed BUDGET requirement for business constraint gaps."""
        gaps: List[ResourceGap] = []
        limitations: List[str] = []

        if requirement_result is None:
            return gaps, limitations

        validation = requirement_result.budget_validation
        if validation is None:
            gaps.append(
                ResourceGap(
                    gap_type=GapType.BUDGET_UNAVAILABLE,
                    resource_type=ResourceType.BUDGET,
                    gap_description="No budget resource is available for validation",
                    eligible_count=0,
                    excluded_count=0,
                )
            )
            limitations.append(
                "Budget unavailable: escalate for budget allocation or adjustment"
            )
            return gaps, limitations

        checks = (
            validation.sufficient_balance,
            validation.cost_centre_match,
            validation.currency_match,
            validation.validity_period_valid,
            validation.within_authorization_limit,
        )
        if not all(checks):
            gaps.append(
                ResourceGap(
                    gap_type=GapType.BUDGET_UNAVAILABLE,
                    resource_type=ResourceType.BUDGET,
                    gap_description="Budget validation failed with no feasible fallback",
                    eligible_count=0,
                    excluded_count=0,
                )
            )
            limitations.append(
                "Budget constraint detected: review funding, limits, or approval escalation"
            )

        return gaps, limitations

    def detect_human_resource_gap(
        self,
        requirement_result: RequirementResult,
    ) -> Optional[ResourceGap]:
        """Backward-compatible helper returning the first HUMAN gap if present."""
        gaps, _, _ = self.analyze_human_constraint(requirement_result)
        return gaps[0] if gaps else None

    def generate_alternatives(
        self,
        resource_type: ResourceType,
    ) -> List[ResourceAlternative]:
        """Generate alternatives in exact required order."""
        if resource_type != ResourceType.HUMAN:
            return []

        return [
            ResourceAlternative(
                alternative_type=GapAlternativeType.RELAX_NON_MANDATORY_PREFERENCES,
                description=(
                    "Consider relaxing non-mandatory preference criteria "
                    "(preferred skills, preferred roles)"
                ),
                requires_approval=True,
                estimated_effort_hours=Decimal("2"),
                cost_impact=Decimal("0"),
            ),
            ResourceAlternative(
                alternative_type=GapAlternativeType.REBALANCE_WORKLOAD,
                description="Rebalance workload across existing team members to free up capacity",
                requires_approval=True,
                estimated_effort_hours=Decimal("8"),
                cost_impact=Decimal("0"),
            ),
            ResourceAlternative(
                alternative_type=GapAlternativeType.RESCHEDULE_DEADLINE,
                description="Reschedule the task deadline to allow for resource availability",
                requires_approval=True,
                estimated_effort_hours=Decimal("1"),
                cost_impact=Decimal("0"),
            ),
            ResourceAlternative(
                alternative_type=GapAlternativeType.TEMPORARY_INTERNAL_SUPPORT,
                description="Assign temporary internal support from another department",
                requires_approval=True,
                estimated_effort_hours=Decimal("4"),
                cost_impact=Decimal("500"),
            ),
            ResourceAlternative(
                alternative_type=GapAlternativeType.TRAIN_OR_UPSKILL,
                description="Train or upskill existing team members to meet requirements",
                requires_approval=True,
                estimated_effort_hours=Decimal("40"),
                cost_impact=Decimal("2000"),
            ),
            ResourceAlternative(
                alternative_type=GapAlternativeType.APPROVED_EXTERNAL_SERVICE,
                description="Engage an approved external service provider or contractor",
                requires_approval=True,
                estimated_effort_hours=Decimal("2"),
                cost_impact=Decimal("10000"),
            ),
            ResourceAlternative(
                alternative_type=GapAlternativeType.RECRUITMENT_ESCALATION,
                description="Escalate to recruitment process to hire new personnel",
                requires_approval=True,
                estimated_effort_hours=Decimal("80"),
                cost_impact=Decimal("50000"),
            ),
        ]
