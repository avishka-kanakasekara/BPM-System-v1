"""TO-BE recommendations: evidence-backed, never auto-activate workflows."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.monitoring.analytics import calculate_kpis, step_duration
from app.monitoring.records import MonitoringProcess
from app.monitoring.schemas import (
    RecommendationEvidence,
    TobeRecommendationRecord,
)
from app.monitoring.store import MonitoringStore, get_monitoring_store
from app.policy_knowledge.constants import PolicyRuleType
from app.policy_knowledge.retrieval import PolicyRetrievalService

FORBIDDEN_TYPES: dict[str, frozenset[PolicyRuleType]] = {
    "remove_mandatory_approval": frozenset(
        {PolicyRuleType.APPROVAL_THRESHOLD, PolicyRuleType.REQUIRED_AUTHORIZATION}
    ),
    "bypass_sod": frozenset({PolicyRuleType.SEGREGATION_OF_DUTIES}),
    "remove_quotation_requirement": frozenset({PolicyRuleType.REQUIRED_EVIDENCE}),
    "remove_budget_control": frozenset({PolicyRuleType.BUDGET_LIMIT}),
    "reduce_required_evidence": frozenset({PolicyRuleType.REQUIRED_EVIDENCE}),
    "change_approval_authority": frozenset({PolicyRuleType.REQUIRED_AUTHORIZATION}),
    "bypass_policy": frozenset(set(PolicyRuleType)),
}

ALLOWED_REVIEW_ROLES = frozenset({"approver", "admin"})


def _fingerprint(
    tenant_id: UUID,
    process_id: UUID | None,
    rec_type: str,
    evidence: list[RecommendationEvidence],
) -> str:
    payload = {
        "tenant_id": str(tenant_id),
        "process_id": None if process_id is None else str(process_id),
        "recommendation_type": rec_type,
        "evidence": [
            {
                "workflow_step_id": None if item.workflow_step_id is None else str(item.workflow_step_id),
                "field": item.field,
                "value": item.value,
                "source": item.source,
            }
            for item in evidence
        ],
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _kpi_snapshot(process: MonitoringProcess) -> dict:
    report = calculate_kpis(process.tenant_id, [process], process_id=process.process_id)
    dump = report.model_dump(mode="json")
    dump.pop("bottleneck_steps", None)
    return dump


async def evaluate_policy(
    *,
    tenant_id: UUID,
    recommendation_type: str,
    policy_retrieval: PolicyRetrievalService | None,
) -> tuple[str, str | None]:
    """Return (policy_status, reason). Uses retrieved rules; does not hardcode thresholds."""
    if recommendation_type not in FORBIDDEN_TYPES:
        return "ALLOWED", None
    conflicting_types = FORBIDDEN_TYPES[recommendation_type]
    if policy_retrieval is None:
        return "NOT_ALLOWED", "policy_evaluation_required"
    versions = await policy_retrieval._repository.list_active_versions(tenant_id)
    active_types = {
        rule.rule_type
        for _policy, version in versions
        for rule in version.rules
    }
    hits = sorted(item.value for item in conflicting_types if item in active_types)
    if hits:
        return "NOT_ALLOWED", f"conflicts_with_policy_rule_types:{','.join(hits)}"
    # Forbidden control-removal types are never allowed even if a tenant has not
    # loaded a matching rule — safety default, not a numeric threshold.
    return "NOT_ALLOWED", "mandatory_control_removal_not_allowed"


class TobeRecommendationService:
    def __init__(
        self,
        store: MonitoringStore | None = None,
        policy_retrieval: PolicyRetrievalService | None = None,
    ) -> None:
        self._store = store or get_monitoring_store()
        self._policy_retrieval = policy_retrieval

    def list(self, tenant_id: UUID, process_id: UUID | None = None) -> list[TobeRecommendationRecord]:
        return self._store.list_recommendations(tenant_id, process_id=process_id)

    def get(self, tenant_id: UUID, recommendation_id: UUID) -> TobeRecommendationRecord:
        record = self._store.get_recommendation(tenant_id, recommendation_id)
        if record is None:
            raise RecommendationNotFoundError(recommendation_id)
        return record

    async def generate(
        self,
        tenant_id: UUID,
        process_id: UUID,
        *,
        include_forbidden: str | None = None,
    ) -> list[TobeRecommendationRecord]:
        process = self._store.get_process(tenant_id, process_id)
        if process is None:
            raise ProcessMissingError(process_id)
        candidates = _candidates_from_evidence(process)
        if include_forbidden:
            candidates.append(_forbidden_stub(process, include_forbidden))
        if not candidates:
            return []
        persisted: list[TobeRecommendationRecord] = []
        for item in candidates:
            policy_status, policy_reason = await evaluate_policy(
                tenant_id=tenant_id,
                recommendation_type=item["recommendation_type"],
                policy_retrieval=self._policy_retrieval,
            )
            if policy_status == "NOT_ALLOWED":
                item["status"] = "NOT_ALLOWED"
                item["reason"] = policy_reason or item["reason"]
                item["policy_status"] = "NOT_ALLOWED"
            fingerprint = _fingerprint(
                tenant_id, process_id, item["recommendation_type"], item["evidence"]
            )
            record = TobeRecommendationRecord(
                tenant_id=tenant_id,
                process_id=process_id,
                workflow_plan_id=process.workflow_plan_id,
                recommendation_type=item["recommendation_type"],
                title=item["title"],
                description=item["description"],
                reason=item["reason"],
                evidence=item["evidence"],
                kpi_snapshot=_kpi_snapshot(process),
                expected_benefit=item.get("expected_benefit"),
                risk=item.get("risk"),
                confidence=item.get("confidence"),
                status=item.get("status", "PROPOSED"),
                fingerprint=fingerprint,
                created_at=datetime.now(UTC),
                activates_workflow=False,
                policy_status=item.get("policy_status", policy_status),
            )
            persisted.append(self._store.upsert_recommendation(record))
        return persisted

    def review(
        self,
        tenant_id: UUID,
        recommendation_id: UUID,
        *,
        decision: str,
        reviewer_id: UUID,
        role: str,
    ) -> TobeRecommendationRecord:
        if role not in ALLOWED_REVIEW_ROLES:
            raise RecommendationReviewForbiddenError(role)
        existing = self.get(tenant_id, recommendation_id)
        if existing.status == "NOT_ALLOWED":
            raise RecommendationNotReviewableError(recommendation_id)
        if existing.status not in {"PROPOSED"}:
            return existing
        updated = existing.model_copy(
            update={
                "status": decision,
                "reviewed_at": datetime.now(UTC),
                "reviewed_by": reviewer_id,
                "activates_workflow": False,
            }
        )
        self._store.replace_recommendation(updated)
        return updated


def _forbidden_stub(process: MonitoringProcess, rec_type: str) -> dict:
    return {
        "recommendation_type": rec_type,
        "title": "Remove mandatory control",
        "description": "Unsafe control-removal proposal used only to verify policy gating.",
        "reason": "policy_conflict_probe",
        "evidence": [
            RecommendationEvidence(
                workflow_step_id=None,
                field="recommendation_type",
                value=rec_type,
                source="policy_probe",
            )
        ],
        "expected_benefit": None,
        "risk": "Would weaken mandatory controls",
        "confidence": Decimal("0.1000"),
    }


def _candidates_from_evidence(process: MonitoringProcess) -> list[dict]:
    candidates: list[dict] = []
    durations = [step_duration(step) for step in process.steps]
    independent = [
        step
        for step in process.steps
        if not step.depends_on_step_keys
        and step.step_type in {"VALIDATION", "DOCUMENT_REVIEW"}
    ]
    if len(independent) >= 2:
        a, b = independent[0], independent[1]
        evidence = [
            RecommendationEvidence(
                workflow_step_id=a.workflow_step_id,
                field="depends_on_step_keys",
                value=a.depends_on_step_keys,
                source="workflow_dependency",
            ),
            RecommendationEvidence(
                workflow_step_id=b.workflow_step_id,
                field="depends_on_step_keys",
                value=b.depends_on_step_keys,
                source="workflow_dependency",
            ),
            RecommendationEvidence(
                workflow_step_id=a.workflow_step_id,
                field="duration_seconds",
                value=None
                if step_duration(a).duration_seconds is None
                else str(step_duration(a).duration_seconds),
                source="step_duration",
            ),
            RecommendationEvidence(
                workflow_step_id=b.workflow_step_id,
                field="duration_seconds",
                value=None
                if step_duration(b).duration_seconds is None
                else str(step_duration(b).duration_seconds),
                source="step_duration",
            ),
        ]
        candidates.append(
            {
                "recommendation_type": "parallelize_independent_steps",
                "title": f"Parallelize {a.name} and {b.name}",
                "description": "Both steps have no recorded dependency on each other.",
                "reason": "Both steps have no dependency on each other",
                "evidence": evidence,
                "expected_benefit": "Reduce elapsed process time by overlapping independent work",
                "risk": "Must preserve evidence and approval gates; does not activate a plan",
                "confidence": Decimal("0.7200"),
            }
        )

    waits = [item for item in durations if item.human_wait_seconds is not None]
    if waits:
        slowest = max(waits, key=lambda item: item.human_wait_seconds or Decimal("0"))
        candidates.append(
            {
                "recommendation_type": "reduce_approval_delay",
                "title": f"Reduce waiting time for {slowest.name}",
                "description": "Keep the approval step; improve assignment/SLA around it.",
                "reason": "highest observed human wait on an approval/human task",
                "evidence": [
                    RecommendationEvidence(
                        workflow_step_id=slowest.workflow_step_id,
                        field="human_wait_seconds",
                        value=str(slowest.human_wait_seconds),
                        source="approval_timestamps",
                    )
                ],
                "expected_benefit": "Lower human wait without removing the approval control",
                "risk": "Must not change approval authority or SoD",
                "confidence": Decimal("0.6800"),
            }
        )

    codes = [item.code for item in process.exceptions]
    if any(code in {"INVOICE_MISMATCH", "AMOUNT_MISMATCH", "QUANTITY_MISMATCH"} for code in codes):
        candidates.append(
            {
                "recommendation_type": "improve_invoice_matching_workflow",
                "title": "Improve invoice matching checks",
                "description": "Observed invoice/PO matching exceptions on this process.",
                "reason": "invoice matching exceptions recorded",
                "evidence": [
                    RecommendationEvidence(
                        workflow_step_id=item.workflow_step_id,
                        field="exception_code",
                        value=item.code,
                        source="process_exception",
                    )
                    for item in process.exceptions
                    if item.code in {"INVOICE_MISMATCH", "AMOUNT_MISMATCH", "QUANTITY_MISMATCH"}
                ],
                "expected_benefit": "Catch mismatches earlier with the existing matching engine",
                "risk": "Does not bypass matching or complete the process",
                "confidence": Decimal("0.8000"),
            }
        )
    if any(code in {"BUDGET_EXCEEDED", "SOD_VIOLATION", "POLICY_VIOLATION"} for code in codes):
        candidates.append(
            {
                "recommendation_type": "reduce_repeated_exception_causes",
                "title": "Strengthen pre-execution policy and budget checks",
                "description": "Process recorded policy/budget/SoD exceptions and did not complete.",
                "reason": "blocking exceptions prevent completion",
                "evidence": [
                    RecommendationEvidence(
                        workflow_step_id=item.workflow_step_id,
                        field="exception_code",
                        value=item.code,
                        source="process_exception",
                    )
                    for item in process.exceptions
                ],
                "expected_benefit": "Fewer blocked processes without removing controls",
                "risk": "Must not bypass SoD, budget, or approval policy",
                "confidence": Decimal("0.7500"),
            }
        )
    if any(code == "MISSING_EVIDENCE" for code in codes):
        candidates.append(
            {
                "recommendation_type": "add_missing_evidence_validation",
                "title": "Validate required evidence earlier",
                "description": "Missing-evidence exceptions were persisted.",
                "reason": "MISSING_EVIDENCE recorded",
                "evidence": [
                    RecommendationEvidence(
                        workflow_step_id=item.workflow_step_id,
                        field="exception_code",
                        value=item.code,
                        source="process_exception",
                    )
                    for item in process.exceptions
                    if item.code == "MISSING_EVIDENCE"
                ],
                "expected_benefit": "Fail fast before execution",
                "risk": "Must not reduce required evidence",
                "confidence": Decimal("0.7000"),
            }
        )
    return candidates


class RecommendationNotFoundError(LookupError):
    def __init__(self, recommendation_id: UUID) -> None:
        super().__init__(f"Recommendation {recommendation_id} not found for tenant")
        self.recommendation_id = recommendation_id


class ProcessMissingError(LookupError):
    def __init__(self, process_id: UUID) -> None:
        super().__init__(f"Process {process_id} not found for tenant")
        self.process_id = process_id


class RecommendationReviewForbiddenError(PermissionError):
    def __init__(self, role: str) -> None:
        super().__init__(f"Role {role} cannot review TO-BE recommendations")
        self.role = role


class RecommendationNotReviewableError(ValueError):
    def __init__(self, recommendation_id: UUID) -> None:
        super().__init__(f"Recommendation {recommendation_id} cannot be reviewed")
        self.recommendation_id = recommendation_id
