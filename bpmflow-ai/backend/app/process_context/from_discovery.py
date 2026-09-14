"""Populate ProcessContext from Agent 1 outputs without redesigning Agent 1."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Sequence
from uuid import UUID

from app.agents.agent1_discovery.schemas import Entity, ProcessJSON
from app.schemas.agent_message import DiscoveryAgentMessage, EvidenceReference

from .identity import resolve_employee_resource_id
from .schemas import (
    BudgetFacts,
    DiscoveryActivity,
    DiscoveryDependency,
    DiscoverySummary,
    EvidenceItem,
    ProcessContext,
    PurchaseFacts,
    PurchaseItem,
    QuotationFact,
    RequesterIdentity,
)
from .service import decimal_or_none, empty_process_context


def context_from_discovery(
    process: ProcessJSON,
    message: DiscoveryAgentMessage,
    *,
    tenant_id: UUID | None = None,
    requester_user_id: UUID | None = None,
    requester_email: str | None = None,
    requester_name: str | None = None,
    requester_department: str | None = None,
    doc_types: Sequence[str] | None = None,
    documents: Sequence[dict[str, Any]] | None = None,
    entities: Sequence[Entity] | None = None,
) -> ProcessContext:
    """Build a context patch from discovery. Missing facts stay NULL."""
    analytics = process.analytics if isinstance(process.analytics, dict) else {}
    facts = analytics.get("risk_facts") if isinstance(analytics.get("risk_facts"), dict) else {}
    intelligence = (
        analytics.get("document_intelligence")
        if isinstance(analytics.get("document_intelligence"), dict)
        else {}
    )
    mapped = resolve_employee_resource_id(user_id=requester_user_id, tenant_id=tenant_id)
    verified = {
        item.get("field"): item
        for item in (intelligence.get("facts") or [])
        if isinstance(item, dict) and not item.get("abstained") and item.get("value") not in (None, "")
    }
    extracted_name = facts.get("requester") if isinstance(facts.get("requester"), str) else None
    if verified.get("requester"):
        extracted_name = str(verified["requester"]["value"])

    if intelligence.get("status") == "DISCOVERY_CONFLICT" and any(
        (item or {}).get("field") == "amount" for item in (intelligence.get("conflicts") or [])
    ):
        purchase_amount = None
    else:
        purchase_amount = decimal_or_none(
            (verified.get("amount") or {}).get("value") if verified.get("amount") else facts.get("purchase_amount")
        )
    currency = _norm_currency(
        (verified.get("currency") or {}).get("value") if verified.get("currency") else facts.get("currency")
    )
    vendor_name = None
    if verified.get("vendor"):
        vendor_name = str(verified["vendor"]["value"])
    vendor_name = vendor_name or facts.get("vendor_name") or None
    vendor_id = facts.get("vendor_id") or None
    if vendor_id in (None, "") and vendor_name and tenant_id is not None:
        vendor_id = _resolve_vendor_id(tenant_id, vendor_name)
    pr_id = None
    if verified.get("process_request_id"):
        pr_id = str(verified["process_request_id"]["value"])
    pr_id = pr_id or facts.get("purchase_request_id") or None

    items: list[PurchaseItem] = []
    if verified.get("item_description") or verified.get("quantity"):
        items.append(
            PurchaseItem(
                description=str(verified["item_description"]["value"]) if verified.get("item_description") else None,
                quantity=decimal_or_none((verified.get("quantity") or {}).get("value")),
                currency=currency,
            )
        )

    purchase = PurchaseFacts(
        description=process.process_name,
        amount=purchase_amount,
        currency=currency,
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        cost_centre=facts.get("cost_centre") or None,
        purchase_request_id=pr_id,
        items=items,
        amount_source="extracted_evidence" if purchase_amount is not None else "unspecified",
    )
    budget_value = decimal_or_none(
        (verified.get("budget") or {}).get("value") if verified.get("budget") else facts.get("budget_amount")
    )
    budget = (
        BudgetFacts(available_amount=budget_value, currency=currency, source="extracted_evidence")
        if budget_value is not None
        else _budget_from_facts_and_entities(facts, entities)
    )
    quotations = _quotations_from_discovery(
        facts=facts,
        documents=documents or [],
        entities=entities or [],
        evidence_references=message.evidence_references,
        doc_types=doc_types or [],
    )
    evidence = _evidence_from_message(message)
    for pointer in intelligence.get("facts") or []:
        for ref in pointer.get("evidence_refs") or []:
            evidence_id = f"{ref.get('document_id')}:{ref.get('chunk_id')}:{pointer.get('field')}"
            evidence.append(
                EvidenceItem(
                    evidence_id=evidence_id,
                    document_id=UUID(str(ref["document_id"])) if ref.get("document_id") else None,
                    source="agent1_discovery",
                    type=str(pointer.get("field") or "fact"),
                    page=ref.get("page"),
                    section=ref.get("section"),
                    field=str(pointer.get("field") or "fact"),
                )
            )
    quote_count = None
    if verified.get("quotation_count"):
        try:
            quote_count = int(verified["quotation_count"]["value"])
        except (TypeError, ValueError):
            quote_count = None
    if quote_count is None and facts.get("quotation_count") is not None:
        try:
            quote_count = int(facts["quotation_count"])
        except (TypeError, ValueError):
            quote_count = None
    if not quotations and quote_count:
        quote_refs = verified.get("quotation_references")
        labels = quote_refs["value"] if quote_refs and isinstance(quote_refs.get("value"), list) else []
        for index in range(quote_count):
            label = str(labels[index]) if index < len(labels) else f"quotation-{index + 1}"
            quotations.append(
                QuotationFact(
                    quotation_id=label,
                    evidence_id=label,
                    status="extracted",
                    source="extracted_evidence",
                )
            )

    return empty_process_context(message.process_id, tenant_id=tenant_id).model_copy(
        update={
            "requester": RequesterIdentity(
                user_id=requester_user_id,
                employee_resource_id=mapped,
                name=requester_name or extracted_name,
                email=requester_email,
                department=requester_department
                or (
                    str(verified["department"]["value"])
                    if verified.get("department")
                    else None
                ),
                identity_mapped=mapped is not None,
            ),
            "purchase": purchase,
            "budget": budget,
            "quotations": quotations,
            "evidence": evidence,
            "discovery": DiscoverySummary(
                discovery_status=message.status,
                message_id=message.message_id,
                trace_id=message.trace_id,
                activities=[
                    DiscoveryActivity(name=act.name, actor=act.actor, system=act.system)
                    for act in process.activities
                ],
                dependencies=[
                    DiscoveryDependency(predecessor=dep.predecessor, successor=dep.successor)
                    for dep in process.dependencies
                ],
                gaps=list(
                    dict.fromkeys(
                        [
                            *(process.missing_or_contradictory_fields or []),
                            *(intelligence.get("missing") or []),
                        ]
                    )
                ),
            ),
        }
    )


def _resolve_vendor_id(tenant_id: UUID, vendor_ref: str) -> str | None:
    """Bind extracted vendor names to the tenant vendor table. Never invent a vendor."""
    try:
        from app.procurement.exceptions import VendorNotFoundError
        from app.procurement.service import get_procurement

        vendor = get_procurement().resolve_vendor(tenant_id=tenant_id, vendor_ref=vendor_ref)
        return str(vendor.vendor_id)
    except VendorNotFoundError:
        return None
    except Exception:
        return None


def _norm_currency(value: object) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().upper().replace("$", "USD")
    return text or None


def _budget_from_facts_and_entities(
    facts: dict[str, Any],
    entities: Sequence[Entity] | None,
) -> BudgetFacts:
    amount = decimal_or_none(facts.get("budget_amount") or facts.get("available_budget"))
    currency = _norm_currency(facts.get("budget_currency") or facts.get("currency"))
    if amount is None and entities:
        for entity in entities:
            if (entity.entity_type or "").lower() in {"budget", "available_budget", "budget_amount"}:
                amount = _parse_decimal(entity.value)
                break
    if amount is None:
        return BudgetFacts()
    return BudgetFacts(
        available_amount=amount,
        currency=currency,
        source="extracted_evidence",
    )


def _quotations_from_discovery(
    *,
    facts: dict[str, Any],
    documents: Sequence[dict[str, Any]],
    entities: Sequence[Entity],
    evidence_references: Sequence[EvidenceReference],
    doc_types: Sequence[str],
) -> list[QuotationFact]:
    quotations: list[QuotationFact] = []
    quote_docs = [
        doc
        for doc in documents
        if str(doc.get("doc_type") or "").upper() == "QUOTATION"
    ]
    for index, doc in enumerate(quote_docs, start=1):
        file_id = doc.get("file_id")
        doc_uuid = file_id if isinstance(file_id, UUID) else None
        quotations.append(
            QuotationFact(
                quotation_id=str(doc_uuid or f"quotation-{index}"),
                vendor=facts.get("vendor_name"),
                amount=decimal_or_none(facts.get("purchase_amount")) if len(quote_docs) == 1 else None,
                currency=_norm_currency(facts.get("currency")) if len(quote_docs) == 1 else None,
                document_id=doc_uuid,
                evidence_id=str(doc_uuid) if doc_uuid else f"quotation-doc-{index}",
                status="extracted",
            )
        )
    type_count = sum(1 for item in doc_types if str(item).upper() == "QUOTATION")
    if not quotations and type_count:
        for index in range(1, type_count + 1):
            quotations.append(
                QuotationFact(
                    quotation_id=f"quotation-type-{index}",
                    vendor=facts.get("vendor_name"),
                    amount=decimal_or_none(facts.get("purchase_amount")) if type_count == 1 else None,
                    currency=_norm_currency(facts.get("currency")) if type_count == 1 else None,
                    status="extracted",
                )
            )
    quote_entities = [
        entity
        for entity in entities
        if (entity.entity_type or "").lower() in {"quotation", "quote"}
    ]
    if not quotations:
        for index, entity in enumerate(quote_entities, start=1):
            quotations.append(
                QuotationFact(
                    quotation_id=f"quotation-entity-{index}",
                    vendor=entity.value if entity.value and not _looks_like_amount(entity.value) else facts.get("vendor_name"),
                    amount=_parse_decimal(entity.value),
                    currency=_norm_currency(facts.get("currency")),
                    evidence_id=f"entity-quotation-{index}",
                    status="extracted",
                )
            )
    # Evidence refs pointing at quotation fields.
    if not quotations:
        quote_refs = [
            ref for ref in evidence_references if "quot" in (ref.field or "").lower()
        ]
        for index, ref in enumerate(quote_refs, start=1):
            quotations.append(
                QuotationFact(
                    quotation_id=str(ref.file_id),
                    document_id=ref.file_id,
                    evidence_id=str(ref.file_id),
                    status="extracted",
                )
            )
    return quotations


def _evidence_from_message(message: DiscoveryAgentMessage) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for ref in message.evidence_references:
        items.append(
            EvidenceItem(
                evidence_id=f"{ref.file_id}:{ref.field}",
                document_id=ref.file_id,
                source="agent1_discovery",
                type=ref.field,
                page=ref.page,
                field=ref.field,
            )
        )
    return items


def _parse_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    cleaned = (
        str(raw)
        .replace(",", "")
        .replace("LKR", "")
        .replace("USD", "")
        .replace("$", "")
        .strip()
    )
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _looks_like_amount(value: str) -> bool:
    return _parse_decimal(value) is not None
