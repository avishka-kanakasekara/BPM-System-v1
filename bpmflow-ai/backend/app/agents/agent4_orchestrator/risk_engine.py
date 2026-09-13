"""Pure risk evaluators for Agent 4.

Each function inspects ``RiskEvaluationContext`` (including ``risk_facts`` fields
and ``policy_snapshot``) and returns zero or more ``RiskFinding`` records with
severity, evidence, and recommendation. Thresholds come from ``policy_rules``
when a snapshot is attached; legacy constants apply only without policy.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.policy_knowledge.constants import PolicyRetrievalStatus

from .constants import (
    RISK_LEVEL_RANK,
    RiskLevel,
    RiskRecommendation,
    RiskType,
)
from .schemas import RiskEvaluationContext, RiskFinding


def evidence_refs(context: RiskEvaluationContext) -> list[str]:
    snapshot = context.policy_snapshot
    if snapshot is None:
        return []
    refs: list[str] = []
    for item in snapshot.evidence:
        label = f"{item.policy_name} v{item.version}"
        if item.section:
            label = f"{label} §{item.section}"
        elif item.page is not None:
            label = f"{label} p.{item.page}"
        refs.append(label)
    for version in snapshot.policy_versions:
        token = f"policy_version:{version}"
        if token not in refs:
            refs.append(token)
    return refs


def policy_mode(context: RiskEvaluationContext) -> bool:
    return context.policy_snapshot is not None


def evaluate_policy_conflict(context: RiskEvaluationContext) -> list[RiskFinding]:
    snapshot = context.policy_snapshot
    if snapshot is None or snapshot.status is not PolicyRetrievalStatus.CONFLICT:
        return []
    return [
        RiskFinding(
            risk_level=RiskLevel.HIGH,
            risk_type=RiskType.POLICY_CONFLICT,
            description=(
                snapshot.message
                or "Active company policies define conflicting thresholds or controls."
            ),
            recommendation=RiskRecommendation.HUMAN_APPROVAL,
            evidence_refs=evidence_refs(context),
            policy_version=(
                snapshot.policy_versions[0] if snapshot.policy_versions else None
            ),
        )
    ]


def evaluate_policy_uncertainty(context: RiskEvaluationContext) -> list[RiskFinding]:
    snapshot = context.policy_snapshot
    if snapshot is None:
        return []
    if snapshot.status is PolicyRetrievalStatus.CONFLICT:
        return []
    needs_threshold = context.purchase_amount is not None
    missing_threshold = (
        snapshot.high_value_threshold is None and snapshot.approval_threshold is None
    )
    if needs_threshold and (
        snapshot.status
        in (
            PolicyRetrievalStatus.NOT_FOUND,
            PolicyRetrievalStatus.INSUFFICIENT_EVIDENCE,
        )
        or missing_threshold
    ):
        return [
            RiskFinding(
                risk_level=RiskLevel.HIGH,
                risk_type=RiskType.POLICY_UNCERTAINTY,
                description=(
                    "No authoritative active company policy threshold was found for "
                    "this purchase. The process must not continue on an invented rule."
                ),
                recommendation=RiskRecommendation.HUMAN_APPROVAL,
                evidence_refs=evidence_refs(context),
                amount=context.purchase_amount,
                currency=context.currency or snapshot.currency,
            )
        ]
    if context.purchase_amount is None:
        has_threshold = (
            snapshot.high_value_threshold is not None
            or snapshot.approval_threshold is not None
        )
        if has_threshold:
            return [
                RiskFinding(
                    risk_level=RiskLevel.HIGH,
                    risk_type=RiskType.POLICY_UNCERTAINTY,
                    description=(
                        "Company policy defines an approval threshold, but no purchase "
                        "amount could be determined from the submitted process evidence. "
                        "Human review is required before execution."
                    ),
                    recommendation=RiskRecommendation.HUMAN_APPROVAL,
                    evidence_refs=evidence_refs(context),
                    threshold=snapshot.high_value_threshold or snapshot.approval_threshold,
                    currency=snapshot.currency or context.currency,
                )
            ]
    return []


def _resolve_high_value_threshold(
    context: RiskEvaluationContext,
) -> tuple[Decimal, str | None, str | None] | None:
    snapshot = context.policy_snapshot
    if snapshot is not None:
        if snapshot.status is PolicyRetrievalStatus.CONFLICT:
            return None
        if snapshot.high_value_threshold is None:
            return None
        version = snapshot.policy_versions[0] if snapshot.policy_versions else None
        return (
            snapshot.high_value_threshold,
            snapshot.currency or context.currency,
            version,
        )
    return (context.high_value_threshold, context.currency, None)


def evaluate_high_value_purchase(context: RiskEvaluationContext) -> list[RiskFinding]:
    if context.purchase_amount is None:
        return []
    resolved = _resolve_high_value_threshold(context)
    if resolved is None:
        return []
    threshold, currency, policy_version = resolved
    if context.purchase_amount <= threshold:
        return []
    source = (
        "active company policy"
        if policy_mode(context)
        else "configured evaluation threshold"
    )
    return [
        RiskFinding(
            risk_level=RiskLevel.HIGH,
            risk_type=RiskType.HIGH_VALUE_PURCHASE,
            description=(
                f"Purchase amount {context.purchase_amount}"
                f"{f' {currency}' if currency else ''} exceeds the {source} "
                f"high-value threshold {threshold}"
                f"{f' {currency}' if currency else ''}."
            ),
            recommendation=RiskRecommendation.HUMAN_APPROVAL,
            evidence_refs=evidence_refs(context),
            policy_version=policy_version,
            amount=context.purchase_amount,
            threshold=threshold,
            currency=currency,
        )
    ]


def evaluate_approval_threshold(context: RiskEvaluationContext) -> list[RiskFinding]:
    snapshot = context.policy_snapshot
    if snapshot is None or context.purchase_amount is None:
        return []
    if snapshot.status is PolicyRetrievalStatus.CONFLICT:
        return []
    threshold = snapshot.approval_threshold
    if threshold is None:
        return []
    if (
        snapshot.high_value_threshold is not None
        and snapshot.high_value_threshold == threshold
        and context.purchase_amount > threshold
    ):
        return []
    if context.purchase_amount <= threshold:
        return []
    currency = snapshot.currency or context.currency
    return [
        RiskFinding(
            risk_level=RiskLevel.HIGH,
            risk_type=RiskType.APPROVAL_THRESHOLD,
            description=(
                f"Purchase amount {context.purchase_amount}"
                f"{f' {currency}' if currency else ''} exceeds the active policy "
                f"approval threshold {threshold}"
                f"{f' {currency}' if currency else ''}."
            ),
            recommendation=RiskRecommendation.HUMAN_APPROVAL,
            evidence_refs=evidence_refs(context),
            policy_version=(
                snapshot.policy_versions[0] if snapshot.policy_versions else None
            ),
            amount=context.purchase_amount,
            threshold=threshold,
            currency=currency,
        )
    ]


def evaluate_missing_evidence(context: RiskEvaluationContext) -> list[RiskFinding]:
    required = list(context.required_evidence)
    snapshot = context.policy_snapshot
    if snapshot is not None:
        for item in snapshot.required_evidence:
            if item not in required:
                required.append(item)
    provided = {item for item in context.provided_evidence}
    missing = [item for item in required if item not in provided]
    if not missing:
        return []
    recommendation = (
        RiskRecommendation.HUMAN_APPROVAL
        if snapshot is not None
        else RiskRecommendation.REQUEST_EVIDENCE
    )
    return [
        RiskFinding(
            risk_level=RiskLevel.HIGH if snapshot is not None else RiskLevel.MEDIUM,
            risk_type=RiskType.MISSING_EVIDENCE,
            description=f"Required evidence is missing: {', '.join(missing)}.",
            recommendation=recommendation,
            evidence_refs=evidence_refs(context),
        )
    ]


def evaluate_low_confidence(context: RiskEvaluationContext) -> list[RiskFinding]:
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


def evaluate_segregation_of_duties(context: RiskEvaluationContext) -> list[RiskFinding]:
    if context.requester_id is None or context.approver_id is None:
        return []
    if context.requester_id != context.approver_id:
        return []
    snapshot = context.policy_snapshot
    if snapshot is not None and not snapshot.enforce_segregation_of_duties:
        return []
    return [
        RiskFinding(
            risk_level=RiskLevel.HIGH,
            risk_type=RiskType.SEGREGATION_OF_DUTIES,
            description="Requester and approver are the same person.",
            recommendation=RiskRecommendation.REASSIGN_APPROVER,
            evidence_refs=evidence_refs(context),
        )
    ]


def evaluate_unauthorized_action(context: RiskEvaluationContext) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    if context.unauthorized_action:
        findings.append(
            RiskFinding(
                risk_level=RiskLevel.CRITICAL,
                risk_type=RiskType.UNAUTHORIZED_ACTION,
                description="The requested action is marked unauthorized.",
                recommendation=RiskRecommendation.BLOCK_ACTION,
            )
        )
    snapshot = context.policy_snapshot
    if snapshot and snapshot.required_roles:
        requester_roles = {r.upper() for r in context.requester_roles}
        required = {r.upper() for r in snapshot.required_roles}
        if requester_roles.isdisjoint(required):
            findings.append(
                RiskFinding(
                    risk_level=RiskLevel.CRITICAL,
                    risk_type=RiskType.UNAUTHORIZED_ACTION,
                    description=(
                        "Requester lacks policy-required authorization roles: "
                        + ", ".join(sorted(required))
                        + "."
                    ),
                    recommendation=RiskRecommendation.BLOCK_ACTION,
                    evidence_refs=evidence_refs(context),
                )
            )
    return findings


def evaluate_budget_validation_failure(context: RiskEvaluationContext) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    if context.budget_validation_failed:
        findings.append(
            RiskFinding(
                risk_level=RiskLevel.HIGH,
                risk_type=RiskType.BUDGET_VALIDATION_FAILURE,
                description="Budget validation failed for this process.",
                recommendation=RiskRecommendation.HUMAN_APPROVAL,
            )
        )
    available = context.available_budget
    snapshot = context.policy_snapshot
    if available is None and snapshot is not None:
        available = snapshot.available_budget
    if (
        context.purchase_amount is not None
        and available is not None
        and context.purchase_amount > available
    ):
        findings.append(
            RiskFinding(
                risk_level=RiskLevel.HIGH,
                risk_type=RiskType.BUDGET_VALIDATION_FAILURE,
                description=(
                    f"Purchase amount {context.purchase_amount} exceeds available "
                    f"budget {available}."
                ),
                recommendation=RiskRecommendation.HUMAN_APPROVAL,
                amount=context.purchase_amount,
                threshold=available,
                currency=context.currency or (snapshot.currency if snapshot else None),
                evidence_refs=evidence_refs(context),
            )
        )
    return findings


def evaluate_sla_risk(context: RiskEvaluationContext) -> list[RiskFinding]:
    snapshot = context.policy_snapshot
    if snapshot is None or snapshot.sla_hours is None:
        return []
    if context.process_age_hours is None:
        return []
    if context.process_age_hours <= snapshot.sla_hours:
        return []
    return [
        RiskFinding(
            risk_level=RiskLevel.MEDIUM,
            risk_type=RiskType.SLA_RISK,
            description=(
                f"Process age {context.process_age_hours}h exceeds policy SLA "
                f"{snapshot.sla_hours}h."
            ),
            recommendation=RiskRecommendation.HUMAN_APPROVAL,
            evidence_refs=evidence_refs(context),
            threshold=snapshot.sla_hours,
        )
    ]


RISK_EVALUATORS: Sequence = (
    evaluate_policy_conflict,
    evaluate_policy_uncertainty,
    evaluate_high_value_purchase,
    evaluate_approval_threshold,
    evaluate_missing_evidence,
    evaluate_low_confidence,
    evaluate_segregation_of_duties,
    evaluate_unauthorized_action,
    evaluate_budget_validation_failure,
    evaluate_sla_risk,
)


def evaluate_all(context: RiskEvaluationContext) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    for evaluator in RISK_EVALUATORS:
        findings.extend(evaluator(context))
    return findings


def highest_risk_level(findings: list[RiskFinding]) -> RiskLevel | None:
    if not findings:
        return None
    return max(findings, key=lambda item: RISK_LEVEL_RANK[item.risk_level]).risk_level


def context_from_risk_facts(
    base: RiskEvaluationContext,
    facts: dict,
) -> RiskEvaluationContext:
    """Merge Agent 1 ``risk_facts`` into a risk evaluation context."""
    from .risk_facts import merge_context_with_risk_facts

    updates = merge_context_with_risk_facts(
        purchase_amount=base.purchase_amount,
        currency=base.currency,
        provided_evidence=base.provided_evidence,
        confidence=base.confidence,
        facts=facts,
    )
    if not updates:
        return base
    return base.model_copy(update=updates)
