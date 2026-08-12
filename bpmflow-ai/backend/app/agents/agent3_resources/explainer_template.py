"""Template-based explanation generator for Agent 3."""

from typing import List, Optional
from decimal import Decimal

from .schemas import (
    AllocationRecommendation,
    RequirementResult,
    RankedHumanCandidate,
    ResourceGap,
    BudgetValidationResult,
)
from .constants import ResourceType, RecommendationStatus


class TemplateExplainer:
    """Generates deterministic template-based explanations."""

    def generate_explanation(
        self,
        recommendation: AllocationRecommendation,
    ) -> str:
        """Generate a human-readable explanation.
        
        Template includes:
        - Task requirement summary
        - Recommended resource or gap
        - Key eligibility evidence
        - Score summary (if applicable)
        - Limitations
        - Human approval requirement statement
        """
        lines = []
        
        # Task requirement summary
        lines.append("=== Resource Allocation Recommendation ===")
        lines.append("")
        
        # Human resource result
        if recommendation.human_requirement_result:
            lines.append(self._explain_human_result(
                recommendation.human_requirement_result,
            ))
        
        # Budget validation result
        if recommendation.budget_requirement_result:
            lines.append("")
            lines.append(self._explain_budget_result(
                recommendation.budget_requirement_result,
            ))
        
        # Resource gaps
        if recommendation.resource_gaps:
            lines.append("")
            lines.append("=== Resource Gaps ===")
            for gap in recommendation.resource_gaps:
                lines.append(f"- {gap.resource_type}: {gap.gap_description}")
                lines.append(f"  Eligible: {gap.eligible_count}, Excluded: {gap.excluded_count}")
        
        # Alternatives
        if recommendation.alternatives:
            lines.append("")
            lines.append("=== Suggested Alternatives ===")
            for alt in recommendation.alternatives:
                lines.append(f"- {alt.alternative_type}: {alt.description}")
                if alt.estimated_effort_hours:
                    lines.append(f"  Estimated effort: {alt.estimated_effort_hours} hours")
                if alt.cost_impact:
                    lines.append(f"  Cost impact: ${alt.cost_impact}")
        
        # Limitations
        if recommendation.limitations:
            lines.append("")
            lines.append("=== Limitations ===")
            for limitation in recommendation.limitations:
                lines.append(f"- {limitation}")
        
        # Human approval requirement
        lines.append("")
        lines.append("=== Approval Required ===")
        lines.append("This recommendation requires human approval before execution.")
        lines.append("Agent 3 provides evidence-based recommendations but does not make final allocation decisions.")
        
        # Confidence
        lines.append("")
        if recommendation.confidence is not None:
            lines.append(f"Confidence: {recommendation.confidence * 100:.0f}%")
        else:
            lines.append("Confidence: Not calculated")
        
        return "\n".join(lines)

    def _explain_human_result(
        self,
        result: RequirementResult,
    ) -> str:
        """Explain HUMAN resource allocation result."""
        lines = []
        lines.append("=== Human Resource Allocation ===")
        
        if result.eligible_candidates:
            lines.append(f"Found {len(result.eligible_candidates)} eligible candidate(s).")
            lines.append("")
            
            # Top recommendation
            top_candidate = result.eligible_candidates[0]
            lines.append(f"Recommended: {top_candidate.name}")
            lines.append(f"Allocation Score: {top_candidate.allocation_score:.2f}")
            lines.append("")
            lines.append("Score Breakdown:")
            lines.append(f"- Role Match: {top_candidate.score_breakdown.role_match:.2f}")
            lines.append(f"- Skill Match: {top_candidate.score_breakdown.skill_match:.2f}")
            lines.append(f"- Availability: {top_candidate.score_breakdown.availability_score:.2f}")
            lines.append(f"- Workload Fit: {top_candidate.score_breakdown.workload_fit:.2f}")
            lines.append(f"- Authority Match: {top_candidate.score_breakdown.authority_match:.2f}")
            lines.append("")
            lines.append(f"Current Workload: {top_candidate.current_workload_percentage}%")
            lines.append(f"Projected Workload: {top_candidate.projected_workload_percentage}%")
            lines.append(f"Available From: {top_candidate.available_from}")
        else:
            lines.append("No eligible HUMAN resources found.")
        
        if result.excluded_resources:
            lines.append("")
            lines.append(f"Excluded {len(result.excluded_resources)} resource(s):")
            for excluded in result.excluded_resources[:5]:  # Show first 5
                reasons = ", ".join([r.reason for r in excluded.exclusion_reasons])
                lines.append(f"- {excluded.name}: {reasons}")
            if len(result.excluded_resources) > 5:
                lines.append(f"  ... and {len(result.excluded_resources) - 5} more")
        
        return "\n".join(lines)

    def _explain_budget_result(
        self,
        result: RequirementResult,
    ) -> str:
        """Explain BUDGET validation result."""
        lines = []
        lines.append("=== Budget Validation ===")
        
        if result.budget_validation:
            validation = result.budget_validation
            lines.append(f"Budget: {validation.name}")
            lines.append(f"Available Balance: ${validation.available_balance}")
            lines.append(f"Required Amount: ${validation.required_amount}")
            lines.append("")
            lines.append("Validation Checks:")
            lines.append(f"- Sufficient Balance: {'PASS' if validation.sufficient_balance else 'FAIL'}")
            lines.append(f"- Cost Centre Match: {'PASS' if validation.cost_centre_match else 'FAIL'}")
            lines.append(f"- Currency Match: {'PASS' if validation.currency_match else 'FAIL'}")
            lines.append(f"- Validity Period: {'PASS' if validation.validity_period_valid else 'FAIL'}")
            lines.append(f"- Authorization Limit: {'PASS' if validation.within_authorization_limit else 'FAIL'}")
        else:
            lines.append("No budget validation performed.")
        
        return "\n".join(lines)
