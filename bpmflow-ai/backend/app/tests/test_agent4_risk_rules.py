"""Tests for Agent 4 deterministic risk analysis."""

from decimal import Decimal
from uuid import uuid4

from app.agents.agent4_orchestrator import (
    HIGH_VALUE_PURCHASE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
    RiskAnalysisEngine,
    RiskEvaluationContext,
    RiskLevel,
    RiskRecommendation,
    RiskType,
)


def _types(assessment):
    return {finding.risk_type for finding in assessment.findings}


class TestNoRisk:
    def test_normal_purchase_has_no_risk(self) -> None:
        person = uuid4()
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                purchase_amount=HIGH_VALUE_PURCHASE_THRESHOLD,
                required_evidence=["quote"],
                provided_evidence=["quote"],
                confidence=Decimal("0.95"),
                requester_id=person,
                approver_id=uuid4(),
                unauthorized_action=False,
                budget_validation_failed=False,
            )
        )
        assert assessment.risk_detected is False
        assert assessment.findings == []
        assert assessment.overall_risk_level is None


class TestIndividualRules:
    def test_high_value_purchase(self) -> None:
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                purchase_amount=HIGH_VALUE_PURCHASE_THRESHOLD + Decimal("0.01"),
            )
        )
        assert assessment.risk_detected is True
        finding = assessment.findings[0]
        assert finding.risk_type is RiskType.HIGH_VALUE_PURCHASE
        assert finding.risk_level is RiskLevel.HIGH
        assert finding.recommendation is RiskRecommendation.HUMAN_APPROVAL
        assert assessment.overall_risk_level is RiskLevel.HIGH

    def test_missing_evidence(self) -> None:
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                required_evidence=["quote", "spec"],
                provided_evidence=["quote"],
            )
        )
        finding = assessment.findings[0]
        assert finding.risk_type is RiskType.MISSING_EVIDENCE
        assert finding.risk_level is RiskLevel.MEDIUM
        assert finding.recommendation is RiskRecommendation.REQUEST_EVIDENCE
        assert "spec" in finding.description

    def test_low_confidence(self) -> None:
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(confidence=LOW_CONFIDENCE_THRESHOLD - Decimal("0.01"))
        )
        finding = assessment.findings[0]
        assert finding.risk_type is RiskType.LOW_CONFIDENCE
        assert finding.risk_level is RiskLevel.MEDIUM
        assert finding.recommendation is RiskRecommendation.HUMAN_VERIFICATION

    def test_requester_equals_approver(self) -> None:
        same_person = uuid4()
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                requester_id=same_person,
                approver_id=same_person,
            )
        )
        finding = assessment.findings[0]
        assert finding.risk_type is RiskType.SEGREGATION_OF_DUTIES
        assert finding.risk_level is RiskLevel.HIGH
        assert finding.recommendation is RiskRecommendation.REASSIGN_APPROVER

    def test_unauthorized_action(self) -> None:
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(unauthorized_action=True)
        )
        finding = assessment.findings[0]
        assert finding.risk_type is RiskType.UNAUTHORIZED_ACTION
        assert finding.risk_level is RiskLevel.CRITICAL
        assert finding.recommendation is RiskRecommendation.BLOCK_ACTION

    def test_budget_validation_failure(self) -> None:
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(budget_validation_failed=True)
        )
        finding = assessment.findings[0]
        assert finding.risk_type is RiskType.BUDGET_VALIDATION_FAILURE
        assert finding.risk_level is RiskLevel.HIGH
        assert finding.recommendation is RiskRecommendation.HUMAN_APPROVAL


class TestCombinedRisks:
    def test_multiple_risks_are_all_returned(self) -> None:
        same_person = uuid4()
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                purchase_amount=Decimal("50000"),
                required_evidence=["invoice"],
                provided_evidence=[],
                requester_id=same_person,
                approver_id=same_person,
            )
        )
        assert _types(assessment) == {
            RiskType.HIGH_VALUE_PURCHASE,
            RiskType.MISSING_EVIDENCE,
            RiskType.SEGREGATION_OF_DUTIES,
        }
        assert len(assessment.findings) == 3

    def test_highest_risk_level_is_critical_when_unauthorized(self) -> None:
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                purchase_amount=Decimal("50000"),
                confidence=Decimal("0.10"),
                unauthorized_action=True,
            )
        )
        assert RiskType.UNAUTHORIZED_ACTION in _types(assessment)
        assert assessment.overall_risk_level is RiskLevel.CRITICAL


class TestConfigurableThresholds:
    def test_high_value_threshold_override(self) -> None:
        engine = RiskAnalysisEngine()
        amount = Decimal("5000")

        below_custom = engine.evaluate(
            RiskEvaluationContext(
                purchase_amount=amount,
                high_value_threshold=Decimal("10000"),
            )
        )
        above_custom = engine.evaluate(
            RiskEvaluationContext(
                purchase_amount=amount,
                high_value_threshold=Decimal("1000"),
            )
        )

        assert RiskType.HIGH_VALUE_PURCHASE not in _types(below_custom)
        assert RiskType.HIGH_VALUE_PURCHASE in _types(above_custom)

    def test_low_confidence_threshold_override(self) -> None:
        engine = RiskAnalysisEngine()
        confidence = Decimal("0.80")

        passing = engine.evaluate(
            RiskEvaluationContext(
                confidence=confidence,
                low_confidence_threshold=Decimal("0.70"),
            )
        )
        failing = engine.evaluate(
            RiskEvaluationContext(
                confidence=confidence,
                low_confidence_threshold=Decimal("0.90"),
            )
        )

        assert RiskType.LOW_CONFIDENCE not in _types(passing)
        assert RiskType.LOW_CONFIDENCE in _types(failing)
