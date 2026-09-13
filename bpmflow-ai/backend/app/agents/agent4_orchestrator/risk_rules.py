"""Deterministic Agent 4 risk analysis facade.

Delegates to pure functions in ``risk_engine``. Does not approve processes,
change workflow stages, or persist approval_requests.
"""

from .risk_engine import evaluate_all, highest_risk_level
from .schemas import RiskAssessment, RiskEvaluationContext


class RiskAnalysisEngine:
    """Evaluates all configured rules and returns every matching finding."""

    def evaluate(self, context: RiskEvaluationContext) -> RiskAssessment:
        findings = evaluate_all(context)
        return RiskAssessment(
            risk_detected=len(findings) > 0,
            overall_risk_level=highest_risk_level(findings),
            findings=findings,
            policy_snapshot=context.policy_snapshot,
        )
