"""Merge rules for ProcessContext. LLM/agent prose cannot overwrite verified facts."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from .exceptions import MissingRequiredContextError
from .identity import resolve_employee_resource_id
from .schemas import (
    ApproverIdentity,
    BudgetFacts,
    DiscoverySummary,
    EvidenceItem,
    FactSource,
    PolicyRefs,
    ProcessContext,
    PurchaseFacts,
    QuotationFact,
    RequesterIdentity,
    RiskSnapshot,
)

_SOURCE_RANK: dict[FactSource, int] = {
    "authenticated": 5,
    "extracted_evidence": 4,
    "company_repository": 3,
    "policy_repository": 2,
    "agent_derived": 1,
    "unspecified": 0,
}

_PROTECTED_PURCHASE = (
    "amount",
    "currency",
    "vendor_id",
    "vendor_name",
    "cost_centre",
    "purchase_request_id",
)
_PROTECTED_BUDGET = ("budget_id", "allocated_amount", "used_amount", "available_amount", "currency")


def empty_process_context(
    process_id: UUID,
    *,
    tenant_id: UUID | None = None,
    request_id: UUID | None = None,
) -> ProcessContext:
    kwargs: dict[str, Any] = {"process_id": process_id, "tenant_id": tenant_id}
    if request_id is not None:
        kwargs["request_id"] = request_id
    return ProcessContext(**kwargs)


def context_from_process_row(row: Any) -> ProcessContext:
    """Load ProcessContext from an ORM/API process object."""
    process_id = getattr(row, "id", None) or getattr(row, "process_id", None)
    if process_id is None:
        raise ValueError("process row has no id")
    raw = getattr(row, "process_context", None)
    tenant_id = getattr(row, "tenant_id", None)
    if isinstance(raw, dict) and raw:
        ctx = ProcessContext.model_validate(raw)
        if tenant_id and ctx.tenant_id is None:
            ctx = ctx.model_copy(update={"tenant_id": tenant_id})
    else:
        ctx = empty_process_context(process_id, tenant_id=tenant_id)
    created_by = getattr(row, "created_by", None)
    email = getattr(row, "requester_email", None)
    if created_by or email:
        mapped = resolve_employee_resource_id(user_id=created_by, tenant_id=tenant_id)
        ctx = ctx.model_copy(
            update={
                "requester": RequesterIdentity(
                    user_id=created_by,
                    employee_resource_id=mapped,
                    email=email,
                    department=getattr(row, "department", None),
                    identity_mapped=mapped is not None,
                )
            }
        )
    payload = _discovery_payload_from_row(row)
    if payload:
        ctx = _hydrate_from_process_json(ctx, payload)
    return ctx


def _discovery_payload_from_row(row: Any) -> dict[str, Any] | None:
    from app.agents.agent4_orchestrator.risk_facts import risk_facts_from_process_payload

    candidates: list[dict[str, Any]] = []
    process_json = getattr(row, "process_json", None)
    if isinstance(process_json, dict) and process_json:
        candidates.append(process_json)
    meta = getattr(row, "metadata_json", None) or {}
    if isinstance(meta, dict):
        nested = meta.get("process_json")
        if isinstance(nested, dict) and nested:
            candidates.append(nested)
        if meta:
            candidates.append(meta)
    for candidate in candidates:
        facts = risk_facts_from_process_payload(candidate)
        if any(facts.get(key) for key in ("purchase_amount", "currency", "vendor_id", "vendor_name")):
            return candidate
    return candidates[0] if candidates else None


def _hydrate_from_process_json(ctx: ProcessContext, process_json: dict[str, Any]) -> ProcessContext:
    from app.agents.agent4_orchestrator.risk_facts import risk_facts_from_process_payload

    facts = risk_facts_from_process_payload(process_json)
    purchase = PurchaseFacts(
        amount=decimal_or_none(facts.get("purchase_amount")),
        currency=facts.get("currency"),
        vendor_id=facts.get("vendor_id"),
        vendor_name=facts.get("vendor_name"),
        cost_centre=facts.get("cost_centre"),
        amount_source="extracted_evidence" if facts.get("purchase_amount") else "unspecified",
    )
    patch = empty_process_context(ctx.process_id, tenant_id=ctx.tenant_id).model_copy(
        update={"purchase": purchase}
    )
    return merge_process_context(ctx, patch, incoming_source="extracted_evidence")


def apply_verified_patch(
    current: ProcessContext,
    patch: ProcessContext,
    *,
    incoming_source: FactSource,
) -> ProcessContext:
    """Apply patch using source-of-truth precedence. Never invent values."""
    return merge_process_context(current, patch, incoming_source=incoming_source)


def merge_process_context(
    current: ProcessContext,
    incoming: ProcessContext,
    *,
    incoming_source: FactSource,
) -> ProcessContext:
    if incoming.process_id != current.process_id:
        raise ValueError("Cannot merge ProcessContext for a different process_id")
    if (
        current.tenant_id is not None
        and incoming.tenant_id is not None
        and current.tenant_id != incoming.tenant_id
    ):
        raise ValueError("Cannot merge ProcessContext across tenants")

    purchase = _merge_purchase(current.purchase, incoming.purchase, incoming_source)
    budget = _merge_budget(current.budget, incoming.budget, incoming_source)
    quotations = incoming.quotations if incoming.quotations else current.quotations
    evidence = _merge_evidence(current.evidence, incoming.evidence)
    requester = _merge_requester(current.requester, incoming.requester)
    approver = _merge_approver(current.approver, incoming.approver)
    policy = _merge_policy(current.policy, incoming.policy)
    risk = incoming.risk if incoming.risk.findings or incoming.risk.risk_level else current.risk
    discovery = _merge_discovery(current.discovery, incoming.discovery)

    return current.model_copy(
        update={
            "tenant_id": current.tenant_id or incoming.tenant_id,
            "purchase": purchase,
            "budget": budget,
            "quotations": quotations,
            "evidence": evidence,
            "requester": requester,
            "approver": approver,
            "policy": policy,
            "risk": risk,
            "discovery": discovery,
            "updated_at": datetime.now(UTC),
        }
    )


def require_fields(context: ProcessContext, fields: list[str]) -> None:
    missing = context.missing_fields(fields)
    if missing:
        raise MissingRequiredContextError(missing[0], missing_fields=missing)


def _rank(source: FactSource) -> int:
    return _SOURCE_RANK.get(source, 0)


def _keep_existing(existing: object, incoming: object, current_source: FactSource, incoming_source: FactSource) -> object:
    if incoming in (None, "", []):
        return existing
    if existing in (None, "", []):
        return incoming
    if _rank(incoming_source) >= _rank(current_source):
        return incoming
    return existing


def _merge_purchase(current: PurchaseFacts, incoming: PurchaseFacts, source: FactSource) -> PurchaseFacts:
    data = current.model_dump()
    inc = incoming.model_dump()
    current_source = current.amount_source
    for key in _PROTECTED_PURCHASE:
        data[key] = _keep_existing(data.get(key), inc.get(key), current_source, source)
    if inc.get("description"):
        data["description"] = current.description or incoming.description
    if inc.get("purchase_request_id"):
        data["purchase_request_id"] = current.purchase_request_id or incoming.purchase_request_id
    if incoming.items and not current.items:
        data["items"] = inc["items"]
    if incoming.amount is not None and (current.amount is None or _rank(source) >= _rank(current_source)):
        data["amount_source"] = source
    return PurchaseFacts.model_validate(data)


def _merge_budget(current: BudgetFacts, incoming: BudgetFacts, source: FactSource) -> BudgetFacts:
    data = current.model_dump()
    inc = incoming.model_dump()
    current_source = current.source
    for key in _PROTECTED_BUDGET:
        data[key] = _keep_existing(data.get(key), inc.get(key), current_source, source)
    if incoming.available_amount is not None and (
        current.available_amount is None or _rank(source) >= _rank(current_source)
    ):
        data["source"] = source
    return BudgetFacts.model_validate(data)


def _merge_evidence(current: list[EvidenceItem], incoming: list[EvidenceItem]) -> list[EvidenceItem]:
    by_id = {item.evidence_id: item for item in current}
    for item in incoming:
        by_id.setdefault(item.evidence_id, item)
    return list(by_id.values())


def _merge_requester(current: RequesterIdentity, incoming: RequesterIdentity) -> RequesterIdentity:
    user_id = incoming.user_id or current.user_id
    tenant_unmapped = incoming.employee_resource_id or current.employee_resource_id
    return RequesterIdentity(
        user_id=user_id,
        employee_resource_id=tenant_unmapped,
        name=incoming.name or current.name,
        email=incoming.email or current.email,
        department=incoming.department or current.department,
        identity_mapped=incoming.identity_mapped
        or current.identity_mapped
        or tenant_unmapped is not None,
    )


def _merge_approver(current: ApproverIdentity, incoming: ApproverIdentity) -> ApproverIdentity:
    return ApproverIdentity(
        user_id=incoming.user_id or current.user_id,
        employee_resource_id=incoming.employee_resource_id or current.employee_resource_id,
        role=incoming.role or current.role,
        email=incoming.email or current.email,
        approval_id=incoming.approval_id or current.approval_id,
    )


def _merge_policy(current: PolicyRefs, incoming: PolicyRefs) -> PolicyRefs:
    ids = list(dict.fromkeys([*current.policy_ids, *incoming.policy_ids]))
    evidence = list(dict.fromkeys([*current.evidence_ids, *incoming.evidence_ids]))
    return PolicyRefs(
        policy_ids=ids,
        policy_version=incoming.policy_version or current.policy_version,
        evidence_ids=evidence,
    )


def _merge_discovery(current: DiscoverySummary, incoming: DiscoverySummary) -> DiscoverySummary:
    if not incoming.activities and not incoming.gaps and not incoming.discovery_status:
        return current
    return DiscoverySummary(
        discovery_status=incoming.discovery_status or current.discovery_status,
        message_id=incoming.message_id or current.message_id,
        trace_id=incoming.trace_id or current.trace_id,
        activities=incoming.activities or current.activities,
        dependencies=incoming.dependencies or current.dependencies,
        gaps=incoming.gaps or current.gaps,
    )


def decimal_or_none(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))
