"""Tests for template-based explanation generation."""

import pytest
from decimal import Decimal
from uuid import uuid4

from app.tests.conftest import utc_datetime
from app.agents.agent3_resources import (
    TemplateExplainer,
    AllocationRecommendation,
    AgentMessageMetadata,
    RequirementResult,
    RankedHumanCandidate,
    ScoreBreakdown,
    BudgetValidationChecks,
    ResourceGap,
    ResourceType,
    RecommendationStatus,
    MessageType,
)


def _valid_recommendation_kwargs(**overrides):
    base = {
        "status": RecommendationStatus.PENDING_HUMAN_APPROVAL,
        "requires_human_approval": True,
        "explanation": "Template explanation placeholder",
        "confidence": Decimal("0.75"),
        "human_requirement_result": None,
        "budget_requirement_result": None,
        "resource_gaps": [],
        "alternatives": [],
        "limitations": [],
    }
    base.update(overrides)
    return base


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
        """Test that explanation includes human approval requirement."""
        explainer = TemplateExplainer()
        
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_RESPONSE,
        )
        
        recommendation = AllocationRecommendation(
            metadata=metadata,
            **_valid_recommendation_kwargs(),
        )
        
        explanation = explainer.generate_explanation(recommendation)
        
        assert "Approval Required" in explanation
        assert "human approval" in explanation.lower()

    def test_explanation_includes_confidence(self):
        """Test that explanation includes confidence score."""
        explainer = TemplateExplainer()
        
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_RESPONSE,
        )
        
        recommendation = AllocationRecommendation(
            metadata=metadata,
            **_valid_recommendation_kwargs(confidence=Decimal("0.85")),
        )
        
        explanation = explainer.generate_explanation(recommendation)
        
        assert "Confidence:" in explanation
        assert "85%" in explanation

    def test_explanation_includes_score_breakdown(self):
        """Test that explanation includes score breakdown for HUMAN resources."""
        explainer = TemplateExplainer()
        
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_RESPONSE,
        )
        
        candidate = _sample_ranked_candidate()
        
        human_result = RequirementResult(
            resource_type=ResourceType.HUMAN,
            eligible_candidates=[candidate],
            excluded_resources=[],
        )
        
        recommendation = AllocationRecommendation(
            metadata=metadata,
            **_valid_recommendation_kwargs(human_requirement_result=human_result),
        )
        
        explanation = explainer.generate_explanation(recommendation)
        
        assert "Score Breakdown:" in explanation
        assert "Role Match:" in explanation
        assert "Skill Match:" in explanation
        assert "Allocation Score:" in explanation

    def test_explanation_includes_excluded_resources(self):
        """Test that explanation includes excluded resources."""
        from app.agents.agent3_resources import (
            ExcludedResource,
            ExclusionReasonEntry,
            ExclusionReason,
        )
        
        explainer = TemplateExplainer()
        
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_RESPONSE,
        )
        
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
        
        recommendation = AllocationRecommendation(
            metadata=metadata,
            **_valid_recommendation_kwargs(human_requirement_result=human_result),
        )
        
        explanation = explainer.generate_explanation(recommendation)
        
        assert "Excluded" in explanation
        assert "INACTIVE_RESOURCE" in explanation

    def test_explanation_includes_budget_validation(self):
        """Test that explanation includes budget validation."""
        explainer = TemplateExplainer()
        
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_RESPONSE,
        )
        
        budget_validation = BudgetValidationChecks(
            resource_id=uuid4(),
            name="Test Budget",
            sufficient_balance=True,
            cost_centre_match=True,
            currency_match=True,
            validity_period_valid=True,
            within_authorization_limit=True,
            available_balance=Decimal("10000"),
            required_amount=Decimal("5000"),
            evidence_references={},
        )
        
        budget_result = RequirementResult(
            resource_type=ResourceType.BUDGET,
            eligible_candidates=[],
            excluded_resources=[],
            budget_validation=budget_validation,
        )
        
        recommendation = AllocationRecommendation(
            metadata=metadata,
            **_valid_recommendation_kwargs(budget_requirement_result=budget_result),
        )
        
        explanation = explainer.generate_explanation(recommendation)
        
        assert "=== Budget Validation ===" in explanation
        assert "Sufficient Balance:" in explanation

    def test_explanation_includes_gaps_and_alternatives(self):
        """Test that explanation includes gaps and alternatives."""
        from app.agents.agent3_resources import (
            ResourceAlternative,
            GapAlternativeType,
        )
        
        explainer = TemplateExplainer()
        
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_RESPONSE,
        )
        
        gap = ResourceGap(
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
        
        recommendation = AllocationRecommendation(
            metadata=metadata,
            **_valid_recommendation_kwargs(
                resource_gaps=[gap],
                alternatives=[alternative],
            ),
        )
        
        explanation = explainer.generate_explanation(recommendation)
        
        assert "=== Resource Gaps ===" in explanation
        assert "=== Suggested Alternatives ===" in explanation
        assert "RELAX_NON_MANDATORY_PREFERENCES" in explanation

    def test_explanation_deterministic_no_openai(self):
        """Test that explanation is deterministic and does not use OpenAI."""
        explainer = TemplateExplainer()
        
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_RESPONSE,
        )
        
        recommendation = AllocationRecommendation(
            metadata=metadata,
            **_valid_recommendation_kwargs(),
        )
        
        # Generate explanation twice
        explanation1 = explainer.generate_explanation(recommendation)
        explanation2 = explainer.generate_explanation(recommendation)
        
        # Should be identical (deterministic)
        assert explanation1 == explanation2

    def test_explanation_includes_limitations(self):
        """Test that explanation includes limitations."""
        explainer = TemplateExplainer()
        
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_RESPONSE,
        )
        
        recommendation = AllocationRecommendation(
            metadata=metadata,
            **_valid_recommendation_kwargs(limitations=["No eligible resources found"]),
        )
        
        explanation = explainer.generate_explanation(recommendation)
        
        assert "=== Limitations ===" in explanation
        assert "No eligible resources found" in explanation
