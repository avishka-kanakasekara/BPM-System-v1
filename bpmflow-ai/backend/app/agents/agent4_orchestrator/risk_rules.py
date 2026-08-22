"""Deterministic Agent 4 risk analysis.

Identifies risks and recommended controls. Does not approve processes,
change workflow stages, or persist approval_requests.
"""

from typing import List, Optional

from .constants import (
    RISK_LEVEL_RANK,
    RiskLevel,
    RiskRecommendation,
    RiskType,
)
from .schemas import RiskAssessment, RiskEvaluationContext, RiskFinding


class RiskAnalysisEngine:
    """Evaluates all configured rules and returns every matching finding."""

    def evaluate(self, context: RiskEvaluationContext) -> RiskAssessment:
        """Run every rule. Never stop after the first match."""
        findings: List[RiskFinding] = []
        findings.extend(self._high_value_purchase(context))
        findings.extend(self._missing_evidence(context))
        findings.extend(self._low_confidence(context))
        findings.extend(self._segregation_of_duties(context))
        findings.extend(self._unauthorized_action(context))
        findings.extend(self._budget_validation_failure(context))
        return RiskAssessment(
            risk_detected=len(findings) > 0,
            overall_risk_level=self._highest_risk_level(findings),
            findings=findings,
        )

    def _high_value_purchase(self, context: RiskEvaluationContext) -> List[RiskFinding]:
        if context.purchase_amount is None:
            return []
        if context.purchase_amount <= context.high_value_threshold:
            return []
        return [
            RiskFinding(
                risk_level=RiskLevel.HIGH,
                risk_type=RiskType.HIGH_VALUE_PURCHASE,
                description=(
                    f"Purchase amount {context.purchase_amount} exceeds the "
                    f"configurable high-value threshold {context.high_value_threshold}."
                ),
                recommendation=RiskRecommendation.HUMAN_APPROVAL,
            )
        ]

    def _missing_evidence(self, context: RiskEvaluationContext) -> List[RiskFinding]:
        provided = {item for item in context.provided_evidence}
        missing = [item for item in context.required_evidence if item not in provided]
        if not missing:
            return []
        return [
            RiskFinding(
                risk_level=RiskLevel.MEDIUM,
                risk_type=RiskType.MISSING_EVIDENCE,
                description=f"Required evidence is missing: {', '.join(missing)}.",
                recommendation=RiskRecommendation.REQUEST_EVIDENCE,
            )
        ]

    def _low_confidence(self, context: RiskEvaluationContext) -> List[RiskFinding]:
        if context.confidence is None:
            return []
        if context.confidence >= context.low_confidence_threshold:
            return []
        return [
            RiskFinding(
                risk_level=RiskLevel.MEDIUM,
                risk_type=RiskType.LOW_CONFIDENCE,
                description=(
                    f"Agent confidence {context.confidence} is below the "
                    f"configurable threshold {context.low_confidence_threshold}."
                ),
                recommendation=RiskRecommendation.HUMAN_VERIFICATION,
            )
        ]

    def _segregation_of_duties(self, context: RiskEvaluationContext) -> List[RiskFinding]:
        """Requester cannot also be the approver (Agent 3 self-approval concept)."""
        if context.requester_id is None or context.approver_id is None:
            return []
        if context.requester_id != context.approver_id:
            return []
        return [
            RiskFinding(
                risk_level=RiskLevel.HIGH,
                risk_type=RiskType.SEGREGATION_OF_DUTIES,
                description="Requester and approver are the same person.",
                recommendation=RiskRecommendation.REASSIGN_APPROVER,
            )
        ]

    def _unauthorized_action(self, context: RiskEvaluationContext) -> List[RiskFinding]:
        if not context.unauthorized_action:
            return []
        return [
            RiskFinding(
                risk_level=RiskLevel.CRITICAL,
                risk_type=RiskType.UNAUTHORIZED_ACTION,
                description="The requested action is marked unauthorized.",
                recommendation=RiskRecommendation.BLOCK_ACTION,
            )
        ]

    def _budget_validation_failure(self, context: RiskEvaluationContext) -> List[RiskFinding]:
        if not context.budget_validation_failed:
            return []
        return [
            RiskFinding(
                risk_level=RiskLevel.HIGH,
                risk_type=RiskType.BUDGET_VALIDATION_FAILURE,
                description="Budget validation failed for this process.",
                recommendation=RiskRecommendation.HUMAN_APPROVAL,
            )
        ]

    def _highest_risk_level(self, findings: List[RiskFinding]) -> Optional[RiskLevel]:
        if not findings:
            return None
        return max(findings, key=lambda item: RISK_LEVEL_RANK[item.risk_level]).risk_level
