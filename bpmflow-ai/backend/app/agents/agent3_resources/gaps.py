"""Resource gap detection and alternatives for Agent 3."""

from typing import List
from decimal import Decimal

from .schemas import (
    RequirementResult,
    ResourceGap,
    ResourceAlternative,
)
from .constants import ResourceType, GapAlternativeType


class GapDetector:
    """Detects resource gaps and generates ordered alternatives."""

    def detect_human_resource_gap(
        self,
        requirement_result: RequirementResult,
    ) -> ResourceGap:
        """Detect if there is a HUMAN resource gap.
        
        A gap exists when no eligible candidates remain.
        """
        eligible_count = len(requirement_result.eligible_candidates)
        excluded_count = len(requirement_result.excluded_resources)
        
        if eligible_count == 0:
            return ResourceGap(
                resource_type=ResourceType.HUMAN,
                gap_description="No eligible HUMAN resources found for this requirement",
                eligible_count=eligible_count,
                excluded_count=excluded_count,
            )
        
        return None

    def generate_alternatives(
        self,
        resource_type: ResourceType,
    ) -> List[ResourceAlternative]:
        """Generate alternatives in exact required order.
        
        Order for HUMAN resources:
        1. RELAX_NON_MANDATORY_PREFERENCES
        2. REBALANCE_WORKLOAD
        3. RESCHEDULE_DEADLINE
        4. TEMPORARY_INTERNAL_SUPPORT
        5. TRAIN_OR_UPSKILL
        6. APPROVED_EXTERNAL_SERVICE
        7. RECRUITMENT_ESCALATION
        """
        if resource_type != ResourceType.HUMAN:
            # BUDGET, SYSTEM, EQUIPMENT are not human substitutes
            return []
        
        alternatives = [
            ResourceAlternative(
                alternative_type=GapAlternativeType.RELAX_NON_MANDATORY_PREFERENCES,
                description="Consider relaxing non-mandatory preference criteria (preferred skills, preferred roles)",
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
        
        return alternatives
