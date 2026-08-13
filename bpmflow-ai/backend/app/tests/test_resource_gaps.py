"""Tests for resource gap detection and alternatives ordering."""

import pytest
from decimal import Decimal
from uuid import uuid4

from app.tests.conftest import utc_datetime
from app.agents.agent3_resources import (
    GapDetector,
    RequirementResult,
    ResourceType,
    GapAlternativeType,
    GapType,
)


class TestResourceGaps:
    """Test resource gap detection and alternatives ordering."""

    def test_gap_detected_when_no_eligible_candidates(self):
        """Test that gap is detected when no eligible candidates remain."""
        detector = GapDetector()
        
        result = RequirementResult(
            resource_type=ResourceType.HUMAN,
            eligible_candidates=[],
            excluded_resources=[],
        )
        
        gap = detector.detect_human_resource_gap(result)
        
        assert gap is not None
        assert gap.resource_type == ResourceType.HUMAN
        assert gap.gap_type == GapType.NO_ELIGIBLE_HUMAN

    def test_no_gap_when_eligible_candidates_exist(self):
        """Test that no gap is detected when eligible candidates exist."""
        from app.agents.agent3_resources import (
            RankedHumanCandidate,
            ScoreBreakdown,
        )
        
        detector = GapDetector()
        
        candidate = RankedHumanCandidate(
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
        
        result = RequirementResult(
            resource_type=ResourceType.HUMAN,
            eligible_candidates=[candidate],
            excluded_resources=[],
        )
        
        gap = detector.detect_human_resource_gap(result)
        
        assert gap is None

    def test_alternatives_follow_exact_required_order(self):
        """Test that alternatives follow the exact required order."""
        detector = GapDetector()
        
        alternatives = detector.generate_alternatives(ResourceType.HUMAN)
        
        assert len(alternatives) == 7
        
        # Verify exact order
        assert alternatives[0].alternative_type == GapAlternativeType.RELAX_NON_MANDATORY_PREFERENCES
        assert alternatives[1].alternative_type == GapAlternativeType.REBALANCE_WORKLOAD
        assert alternatives[2].alternative_type == GapAlternativeType.RESCHEDULE_DEADLINE
        assert alternatives[3].alternative_type == GapAlternativeType.TEMPORARY_INTERNAL_SUPPORT
        assert alternatives[4].alternative_type == GapAlternativeType.TRAIN_OR_UPSKILL
        assert alternatives[5].alternative_type == GapAlternativeType.APPROVED_EXTERNAL_SERVICE
        assert alternatives[6].alternative_type == GapAlternativeType.RECRUITMENT_ESCALATION

    def test_budget_system_equipment_not_human_substitutes(self):
        """Test that BUDGET, SYSTEM, EQUIPMENT are not human substitutes."""
        detector = GapDetector()
        
        # These resource types should return empty alternatives
        budget_alternatives = detector.generate_alternatives(ResourceType.BUDGET)
        system_alternatives = detector.generate_alternatives(ResourceType.SYSTEM)
        equipment_alternatives = detector.generate_alternatives(ResourceType.EQUIPMENT)
        
        assert len(budget_alternatives) == 0
        assert len(system_alternatives) == 0
        assert len(equipment_alternatives) == 0

    def test_all_alternatives_require_approval(self):
        """Test that all alternatives require approval."""
        detector = GapDetector()
        
        alternatives = detector.generate_alternatives(ResourceType.HUMAN)
        
        for alt in alternatives:
            assert alt.requires_approval is True

    def test_alternatives_have_effort_and_cost_estimates(self):
        """Test that alternatives have effort and cost estimates."""
        detector = GapDetector()
        
        alternatives = detector.generate_alternatives(ResourceType.HUMAN)
        
        for alt in alternatives:
            assert alt.estimated_effort_hours is not None
            assert alt.cost_impact is not None
            assert alt.estimated_effort_hours > 0
            assert alt.cost_impact >= 0

    def test_recruitment_escalation_is_final_alternative(self):
        """Test that recruitment escalation is the final alternative."""
        detector = GapDetector()
        
        alternatives = detector.generate_alternatives(ResourceType.HUMAN)
        
        last_alternative = alternatives[-1]
        assert last_alternative.alternative_type == GapAlternativeType.RECRUITMENT_ESCALATION
