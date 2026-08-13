"""Tests for template-based explanation generation."""

import pytest
from decimal import Decimal
from uuid import uuid4

from app.tests.conftest import utc_datetime
from app.agents.agent3_resources import (
    TemplateExplainer,
    ExplanationContext,
    RequirementResult,
    RankedHumanCandidate,
    ScoreBreakdown,
    BudgetValidationChecks,
    ResourceGap,
    ResourceType,
    GapType,
    ResourceAlternative,
    GapAlternativeType,
)


def _context(**overrides):
    base = {
        "confidence": Decimal("0.75"),
        "human_requirement_result": None,
        "budget_requirement_result": None,
        "resource_gaps": [],
        "alternatives": [],
        "limitations": [],
    }
    base.update(overrides)
    return ExplanationContext(**base)


def _sample_ranked_candidate():
    return RankedHumanCandidate(
        resource_id=uuid4(),
        resource_type=ResourceType.HUMAN,
        name="Test Employee",
        rank=1,
        allocation_score=Decimal("0.225"),
        score_breakdown=ScoreBreakdown(
            role_match=Decimal("0.30"),
            skill_match=Decimal("0.25"),
            availability_score=Decimal("0.20"),
            workload_fit=Decimal("0.15"),
            authority_match=Decimal("0.10"),
            total_score=Decimal("0.225"),
        ),
        current_workload_percentage=Decimal("50"),
        projected_workload_percentage=Decimal("60"),
        available_from=utc_datetime(2026, 1, 1),
        evidence_refs={"availability": {}, "workload": {}},
    )


class TestExplainer:
    """Test template-based explanation generation."""

    def test_explanation_includes_human_approval_requirement(self):
        explainer = TemplateExplainer()
        explanation = explainer.generate_explanation(_context())
        assert "Approval Required" in explanation
        assert "human approval" in explanation.lower()
        assert "No alternative is automatically executed" in explanation

    def test_explanation_includes_confidence(self):
        explainer = TemplateExplainer()
        explanation = explainer.generate_explanation(_context(confidence=Decimal("0.85")))
        assert "Confidence:" in explanation
        assert "85%" in explanation

    def test_explanation_includes_score_breakdown(self):
        explainer = TemplateExplainer()
        human_result = RequirementResult(
            resource_type=ResourceType.HUMAN,
            eligible_candidates=[_sample_ranked_candidate()],
            excluded_resources=[],
        )
        explanation = explainer.generate_explanation(
            _context(human_requirement_result=human_result)
        )
        assert "Score Breakdown:" in explanation
        assert "Allocation Score:" in explanation

    def test_explanation_includes_excluded_resources(self):
        from app.agents.agent3_resources import (
            ExcludedResource,
            ExclusionReasonEntry,
            ExclusionReason,
        )

        explainer = TemplateExplainer()
        excluded = ExcludedResource(
            resource_id=uuid4(),
            resource_type=ResourceType.HUMAN,
            name="Excluded Employee",
            exclusion_reasons=[
                ExclusionReasonEntry(
                    reason=ExclusionReason.INACTIVE_RESOURCE,
                    description="Resource is inactive",
                    evidence_reference="is_active",
                )
            ],
        )
        human_result = RequirementResult(
            resource_type=ResourceType.HUMAN,
            eligible_candidates=[],
            excluded_resources=[excluded],
        )
        explanation = explainer.generate_explanation(
            _context(human_requirement_result=human_result)
        )
        assert "Excluded" in explanation
        assert "INACTIVE_RESOURCE" in explanation

    def test_explanation_includes_budget_validation(self):
        explainer = TemplateExplainer()
        budget_result = RequirementResult(
            resource_type=ResourceType.BUDGET,
            budget_validation=BudgetValidationChecks(
                resource_id=uuid4(),
                name="Test Budget",
                sufficient_balance=True,
                cost_centre_match=True,
                currency_match=True,
                validity_period_valid=True,
                within_authorization_limit=True,
                available_balance=Decimal("10000"),
                required_amount=Decimal("5000"),
            ),
        )
        explanation = explainer.generate_explanation(
            _context(budget_requirement_result=budget_result)
        )
        assert "=== Budget Validation ===" in explanation

    def test_explanation_includes_gaps_and_alternatives(self):
        explainer = TemplateExplainer()
        gap = ResourceGap(
            gap_type=GapType.NO_ELIGIBLE_HUMAN,
            resource_type=ResourceType.HUMAN,
            gap_description="No eligible resources",
            eligible_count=0,
            excluded_count=5,
        )
        alternative = ResourceAlternative(
            alternative_type=GapAlternativeType.RELAX_NON_MANDATORY_PREFERENCES,
            description="Relax preferences",
            requires_approval=True,
            estimated_effort_hours=Decimal("2"),
            cost_impact=Decimal("0"),
        )
        explanation = explainer.generate_explanation(
            _context(resource_gaps=[gap], alternatives=[alternative])
        )
        assert "=== Resource Gaps ===" in explanation
        assert "NO_ELIGIBLE_HUMAN" in explanation
        assert "=== Suggested Alternatives ===" in explanation

    def test_explanation_deterministic_no_openai(self):
        explainer = TemplateExplainer()
        context = _context()
        assert explainer.generate_explanation(context) == explainer.generate_explanation(context)

    def test_explanation_includes_limitations(self):
        explainer = TemplateExplainer()
        explanation = explainer.generate_explanation(
            _context(limitations=["No eligible resources found"])
        )
        assert "=== Limitations ===" in explanation
        assert "No eligible resources found" in explanation
