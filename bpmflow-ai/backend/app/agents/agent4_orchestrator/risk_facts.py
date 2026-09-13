"""Extract decision-critical risk facts from Agent 1 discovery outputs.

Used by Agent 4 risk review when the UI calls /risk-review without an explicit
purchase amount — common after uploading a violated purchase document.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.agents.agent1_discovery.schemas import Entity

# Map Agent 1 document classifications → evidence tokens used by risk rules.
_DOC_TYPE_EVIDENCE: dict[str, str] = {
    "PURCHASE_REQUEST": "purchase_request",
    "QUOTATION": "quotation",
    "INVOICE": "invoice",
    "POLICY": "policy",
    "SOP": "sop",
    "EMAIL": "email",
}

_AMOUNT_TOKEN_RE = re.compile(
    r"(?:(?P<currency_before>LKR|USD|EUR|GBP|\$)\s*)?"
    r"(?P<amount>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s*(?P<currency_after>LKR|USD|EUR|GBP))?",
    re.IGNORECASE,
)
_TOTAL_AMOUNT_RE = re.compile(
    r"total\s+amount\s*[:\-]?\s*(?:(?P<currency>LKR|USD|EUR|GBP|\$)\s*)?"
    r"(?P<amount>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_VENDOR_ID_RE = re.compile(
    r"vendor[_\s-]*id\s*[:\-]?\s*([A-Z0-9][A-Z0-9_-]{1,40})",
    re.IGNORECASE,
)
_POLICY_THRESHOLD_RE = re.compile(
    r"(?:policy\s+)?threshold(?:\s+of)?\s*[:\-]?\s*(?:(USD|EUR|GBP|LKR|\$)\s*)?"
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


class RiskFacts(BaseModel):
    """Agent 4 input contract — validated on every discovery write."""

    purchase_amount: str | None = Field(
        default=None,
        description="Primary purchase amount as decimal string (no currency symbol)",
    )
    currency: str | None = None
    vendor_id: str | None = None
    vendor_name: str | None = None
    cost_centre: str | None = None
    requester: str | None = None
    policy_thresholds: list[str] = Field(default_factory=list)
    provided_evidence: list[str] = Field(default_factory=list)
    amount_candidates: list[str] = Field(default_factory=list)
    budget_amount: str | None = None
    quotation_count: int | None = None
    purchase_request_id: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    degraded: bool = False
    extraction_method: Literal["rules", "llm"] = "rules"

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> object:
        if value is None:
            return None
        text = str(value).strip().upper().replace("$", "USD")
        return text or None

    @field_validator("provided_evidence", mode="before")
    @classmethod
    def _normalize_evidence(cls, value: object) -> list[str]:
        if not value:
            return []
        items = value if isinstance(value, list) else [value]
        normalized: list[str] = []
        seen: set[str] = set()
        for item in items:
            token = str(item).strip().lower()
            if token and token not in seen:
                seen.add(token)
                normalized.append(token)
        return normalized

    @classmethod
    def from_discovery(
        cls,
        entities: Sequence[Entity],
        *,
        doc_types: Sequence[str] | None = None,
        joined_text: str = "",
        degraded: bool = False,
    ) -> RiskFacts:
        raw = _extract_risk_fact_fields(entities, doc_types=doc_types, joined_text=joined_text)
        confidence = _confidence_from_entities(entities, raw)
        return cls.model_validate(
            {
                **raw,
                "confidence": confidence,
                "degraded": degraded,
                "extraction_method": "rules",
            }
        )


def _parse_amount(raw: str) -> tuple[Decimal | None, str | None]:
    text = (raw or "").strip()
    if not text:
        return None, None
    match = _AMOUNT_TOKEN_RE.search(text)
    if not match:
        return None, None
    try:
        amount = Decimal(match.group("amount").replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None, None
    currency = match.group("currency_before") or match.group("currency_after")
    if currency == "$":
        currency = "USD"
    elif currency:
        currency = currency.upper()
    return amount, currency


def _amounts_from_text(text: str) -> tuple[list[Decimal], str | None, Decimal | None]:
    """Prefer explicit total lines over subtotals."""
    currency: str | None = None
    totals: list[Decimal] = []
    for match in _TOTAL_AMOUNT_RE.finditer(text or ""):
        try:
            amount = Decimal(match.group("amount").replace(",", ""))
        except (InvalidOperation, AttributeError):
            continue
        totals.append(amount)
        cur = match.group("currency")
        if cur and currency is None:
            currency = "USD" if cur == "$" else cur.upper()
    if totals:
        return totals, currency, max(totals)
    return [], currency, None


def _confidence_from_entities(entities: Sequence[Entity], raw: dict[str, Any]) -> float:
    scores: list[float] = [entity.confidence for entity in entities if entity.confidence]
    base = sum(scores) / len(scores) if scores else 0.55
    if raw.get("purchase_amount"):
        base = max(base, 0.72)
    if raw.get("vendor_id"):
        base = max(base, 0.75)
    if raw.get("provided_evidence"):
        base = max(base, 0.68)
    return round(min(base, 1.0), 4)


def _extract_risk_fact_fields(
    entities: Sequence[Entity],
    *,
    doc_types: Sequence[str] | None = None,
    joined_text: str = "",
) -> dict[str, Any]:
    amounts: list[Decimal] = []
    currency: str | None = None
    provided: list[str] = []
    seen_evidence: set[str] = set()
    vendor_id: str | None = None
    vendor_name: str | None = None
    cost_centre: str | None = None
    requester: str | None = None
    policy_thresholds: list[str] = []

    text_amounts, text_currency, text_total = _amounts_from_text(joined_text)
    if text_currency and currency is None:
        currency = text_currency
    if text_amounts:
        amounts.extend(text_amounts)

    vendor_match = _VENDOR_ID_RE.search(joined_text or "")
    if vendor_match:
        vendor_id = vendor_match.group(1).upper()

    for match in _POLICY_THRESHOLD_RE.finditer(joined_text or ""):
        cur = match.group(1)
        amount = match.group(2).replace(",", "")
        cur_norm = "USD" if cur == "$" else (cur.upper() if cur else currency or "USD")
        token = f"{cur_norm} {amount}"
        if token not in policy_thresholds:
            policy_thresholds.append(token)

    for entity in entities:
        et = (entity.entity_type or "").lower()
        if et in {"amount", "money", "total", "value"}:
            parsed, cur = _parse_amount(entity.value)
            if parsed is not None:
                amounts.append(parsed)
                if cur and currency is None:
                    currency = cur
        if et == "currency" and entity.value:
            currency = currency or str(entity.value).upper().replace("$", "USD")
        if et in {"quotation", "quote", "invoice", "po", "purchase_order", "receipt"}:
            token = "quotation" if et in {"quotation", "quote"} else (
                "po" if et in {"po", "purchase_order"} else et
            )
            if token not in seen_evidence:
                seen_evidence.add(token)
                provided.append(token)
        if et == "supplier" and entity.value and not vendor_name:
            vendor_name = entity.value.strip()
        if et == "cost_centre" and entity.value and not cost_centre:
            cost_centre = entity.value.strip()
        if et == "requester" and entity.value and not requester:
            requester = entity.value.strip()
        if et == "policy_threshold" and entity.value:
            token = entity.value.strip()
            if token not in policy_thresholds:
                policy_thresholds.append(token)

    for doc_type in doc_types or []:
        token = _DOC_TYPE_EVIDENCE.get(str(doc_type).upper())
        if token and token not in seen_evidence:
            seen_evidence.add(token)
            provided.append(token)

    purchase_amount = text_total if text_total is not None else (max(amounts) if amounts else None)
    return {
        "purchase_amount": str(purchase_amount) if purchase_amount is not None else None,
        "currency": currency,
        "vendor_id": vendor_id,
        "vendor_name": vendor_name,
        "cost_centre": cost_centre,
        "requester": requester,
        "policy_thresholds": policy_thresholds,
        "provided_evidence": provided,
        "amount_candidates": [str(a) for a in sorted(set(amounts), reverse=True)],
    }


def extract_risk_facts(
    entities: Sequence[Entity],
    *,
    doc_types: Sequence[str] | None = None,
    joined_text: str = "",
    degraded: bool = False,
) -> dict[str, Any]:
    """Build structured facts for Agent 4 from discovery entities/doc types."""
    return RiskFacts.from_discovery(
        entities,
        doc_types=doc_types,
        joined_text=joined_text,
        degraded=degraded,
    ).model_dump(mode="json")


def validate_risk_facts(payload: dict[str, Any] | None) -> RiskFacts:
    """Validate persisted or in-flight risk_facts; raises on invalid shape."""
    if not isinstance(payload, dict):
        return RiskFacts(degraded=True, confidence=0.0)
    return RiskFacts.model_validate(payload)


def risk_facts_from_process_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Read risk_facts embedded in persisted discovery process_json."""
    if not isinstance(payload, dict):
        return {}
    analytics = payload.get("analytics")
    if isinstance(analytics, dict):
        facts = analytics.get("risk_facts")
        if isinstance(facts, dict):
            return validate_risk_facts(facts).model_dump(mode="json")
    facts = payload.get("risk_facts")
    if isinstance(facts, dict):
        return validate_risk_facts(facts).model_dump(mode="json")
    return {}


def merge_context_with_risk_facts(
    *,
    purchase_amount: Decimal | None,
    currency: str | None,
    provided_evidence: Iterable[str],
    confidence: Decimal | None,
    facts: dict[str, Any],
    discovery_confidence: Decimal | None = None,
) -> dict[str, Any]:
    """Fill missing RiskEvaluationContext fields from discovery risk_facts."""
    validated = validate_risk_facts(facts)
    updates: dict[str, Any] = {}
    if purchase_amount is None and validated.purchase_amount is not None:
        try:
            updates["purchase_amount"] = Decimal(str(validated.purchase_amount))
        except (InvalidOperation, TypeError, ValueError):
            pass
    if not currency and validated.currency:
        updates["currency"] = validated.currency
    provided = list(provided_evidence)
    for item in validated.provided_evidence:
        token = str(item).strip().lower()
        if token and token not in provided:
            provided.append(token)
    if provided != list(provided_evidence):
        updates["provided_evidence"] = provided
    if confidence is None and discovery_confidence is not None:
        updates["confidence"] = discovery_confidence
    elif confidence is None and validated.confidence:
        updates["confidence"] = Decimal(str(validated.confidence))
    return updates
