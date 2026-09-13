"""Evidence-first procurement fact extraction.

Numeric and identity facts come from retrieved/parsed evidence only.
LLM output is never authoritative here. Missing or conflicting values abstain.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.ir.hybrid import IndexedChunk
from app.ir.schemas import EvidencePointer

DiscoveryStatus = Literal["OK", "INSUFFICIENT_EVIDENCE", "DISCOVERY_CONFLICT"]
CRITICAL_LOW_CONFIDENCE = 0.55

_AMOUNT_LABEL_RE = re.compile(
    r"(?:total\s+amount|purchase\s+amount|requested\s+amount|grand\s+total|"
    r"amount\s+requested|total(?:\s+cost)?)\s*[:\-]\s*"
    r"(?:(?P<currency>LKR|USD|EUR|GBP|\$)\s*)?"
    r"(?P<amount>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s*(?P<currency_after>LKR|USD|EUR|GBP))?",
    re.IGNORECASE,
)
_BUDGET_RE = re.compile(
    r"(?:available\s+budget|budget\s+available|budget(?:\s+amount)?)\s*[:\-]\s*"
    r"(?:(?P<currency>LKR|USD|EUR|GBP|\$)\s*)?"
    r"(?P<amount>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s*(?P<currency_after>LKR|USD|EUR|GBP))?",
    re.IGNORECASE,
)
_CURRENCY_RE = re.compile(r"\bcurrency\s*[:\-]\s*(LKR|USD|EUR|GBP)\b", re.IGNORECASE)
_ISO_CURRENCY_RE = re.compile(r"\b(LKR|USD|EUR|GBP)\b", re.IGNORECASE)
_PR_ID_RE = re.compile(r"\b(PR-\d{4}-\d{4,})\b", re.IGNORECASE)
_PO_RE = re.compile(r"\b(?:purchase\s+order|po)\s*(?:number|no\.?|#)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/]{2,40})", re.IGNORECASE)
_NAME_STOP = (
    r"Department|Item|Quantity|Vendor|Currency|Total|Available|Number|"
    r"Approver|Justification|PR\b|Purchase|Quotation"
)
_REQUESTER_RE = re.compile(
    rf"(?:requester|requested\s+by)\s*[:\-]\s*"
    rf"([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+)*)(?=\s*(?:{_NAME_STOP})|\s+[a-z]|\s*$)",
    re.IGNORECASE | re.MULTILINE,
)
_APPROVER_RE = re.compile(
    rf"(?:approver|approved\s+by)\s*[:\-]\s*"
    rf"([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+)*)(?=\s*(?:{_NAME_STOP})|\s+[a-z]|\s*$)",
    re.IGNORECASE | re.MULTILINE,
)
_DEPARTMENT_RE = re.compile(r"department\s*[:\-]\s*([A-Za-z][A-Za-z0-9 &/.-]{1,80})", re.IGNORECASE)
_VENDOR_RE = re.compile(
    r"(?:vendor|supplier)\s*(?:name)?\s*[:\-]\s*([A-Z][A-Za-z0-9&.,' \-]{2,80})",
    re.IGNORECASE,
)
_QTY_RE = re.compile(
    r"(?:quantity|qty)\s*[:\-]\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_ITEM_RE = re.compile(
    r"(?:item(?:s)?|description)\s*[:\-]\s*([^\n]{3,160})",
    re.IGNORECASE,
)
_QUOTE_COUNT_RE = re.compile(
    r"(?:number\s+of\s+quotations|quotations?\s+(?:attached|obtained|received|count)|"
    r"quote(?:s)?\s+(?:attached|obtained|count))\s*[:\-]?\s*(\d+)",
    re.IGNORECASE,
)
_QUOTE_ID_RE = re.compile(r"\b(Q-\d+|[A-Z]{1,5}-\d{2,6}|quotation\s+\d+)\b", re.IGNORECASE)
_JUSTIFICATION_RE = re.compile(r"justification\s*[:\-]\s*([^\n]{3,240})", re.IGNORECASE)
_POLICY_REF_RE = re.compile(
    r"(PROC-POL-[A-Z0-9.\-]+|procurement policy(?:\s+v?[\d.]+)?)",
    re.IGNORECASE,
)

_FORBIDDEN_DEFAULTS = {
    "5000",
    "2500",
    "vendor-acme",
    "it-ops",
    "developer",
    "python",
    "fastapi",
}


class ExtractedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[EvidencePointer] = Field(default_factory=list)
    abstained: bool = False
    reason: str | None = None


class DiscoveryConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = "DISCOVERY_CONFLICT"
    field: str
    candidate_values: list[str]
    evidence_refs: list[EvidencePointer] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.4)
    reason: str


class ProcurementExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: DiscoveryStatus = "OK"
    facts: list[ExtractedFact] = Field(default_factory=list)
    conflicts: list[DiscoveryConflict] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    policy_refs: list[EvidencePointer] = Field(default_factory=list)


def _parse_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(str(raw).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _currency_token(before: str | None, after: str | None) -> str | None:
    token = before or after
    if not token:
        return None
    if token == "$":
        return "USD"
    return token.upper()


def _pointer(chunk: IndexedChunk) -> EvidencePointer:
    return EvidencePointer(
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        page=chunk.page,
        document_version=chunk.document_version,
        source=chunk.source or chunk.filename,
        section=chunk.section,
    )


def _collect_labeled(
    chunks: list[IndexedChunk],
    pattern: re.Pattern[str],
    *,
    group: str | int = 1,
) -> list[tuple[str, IndexedChunk]]:
    found: list[tuple[str, IndexedChunk]] = []
    seen: set[tuple[str, UUID]] = set()
    for chunk in chunks:
        for match in pattern.finditer(chunk.text or ""):
            if isinstance(group, int):
                value = match.group(group)
            else:
                value = match.group(group)
            if not value:
                continue
            cleaned = " ".join(str(value).strip().split())
            key = (cleaned.lower(), chunk.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            found.append((cleaned, chunk))
    return found


def _unique_or_conflict(
    pairs: list[tuple[str, IndexedChunk]],
    *,
    field: str,
    normalize=None,
) -> tuple[str | None, list[IndexedChunk], DiscoveryConflict | None]:
    if not pairs:
        return None, [], None
    buckets: dict[str, list[tuple[str, IndexedChunk]]] = {}
    for raw, chunk in pairs:
        key = str(normalize(raw) if normalize else raw).strip()
        if not key:
            continue
        buckets.setdefault(key.lower() if not isinstance(key, Decimal) else str(key), []).append((str(key), chunk))
    if len(buckets) > 1:
        refs = [_pointer(chunk) for _, chunk in pairs]
        display_values = sorted({item[0] for items in buckets.values() for item in items})
        return None, [chunk for _, chunk in pairs], DiscoveryConflict(
            field=field,
            candidate_values=display_values,
            evidence_refs=refs,
            reason=f"Conflicting evidence for {field}",
        )
    only = next(iter(buckets.values()))
    return only[0][0], [chunk for _, chunk in only], None


def _fact(
    field: str,
    value: Any,
    chunks: list[IndexedChunk],
    *,
    confidence: float,
) -> ExtractedFact:
    return ExtractedFact(
        field=field,
        value=value,
        confidence=confidence,
        evidence_refs=[_pointer(chunk) for chunk in chunks],
    )


def extract_procurement_facts(chunks: list[IndexedChunk]) -> ProcurementExtraction:
    """Extract labeled procurement facts from indexed evidence chunks."""
    facts: list[ExtractedFact] = []
    conflicts: list[DiscoveryConflict] = []
    missing: list[str] = []

    amount_pairs: list[tuple[str, IndexedChunk]] = []
    currency_from_amount: str | None = None
    for chunk in chunks:
        for match in _AMOUNT_LABEL_RE.finditer(chunk.text or ""):
            amount = _parse_decimal(match.group("amount"))
            if amount is None:
                continue
            amount_pairs.append((str(amount), chunk))
            currency_from_amount = currency_from_amount or _currency_token(
                match.group("currency"), match.group("currency_after")
            )

    amount, amount_chunks, amount_conflict = _unique_or_conflict(
        amount_pairs, field="amount", normalize=lambda v: str(_parse_decimal(v) or v)
    )
    if amount_conflict:
        conflicts.append(amount_conflict)
        missing.append("amount")
    elif amount is None:
        missing.append("amount")
        facts.append(
            ExtractedFact(
                field="amount",
                value=None,
                confidence=0.0,
                abstained=True,
                reason="INSUFFICIENT_EVIDENCE",
            )
        )
    else:
        facts.append(_fact("amount", amount, amount_chunks, confidence=0.99))

    budget_pairs: list[tuple[str, IndexedChunk]] = []
    budget_currency: str | None = None
    for chunk in chunks:
        for match in _BUDGET_RE.finditer(chunk.text or ""):
            parsed = _parse_decimal(match.group("amount"))
            if parsed is None:
                continue
            budget_pairs.append((str(parsed), chunk))
            budget_currency = budget_currency or _currency_token(
                match.group("currency"), match.group("currency_after")
            )
    budget, budget_chunks, budget_conflict = _unique_or_conflict(budget_pairs, field="budget")
    if budget_conflict:
        conflicts.append(budget_conflict)
        missing.append("budget")
    elif budget is None:
        missing.append("budget")
        facts.append(
            ExtractedFact(
                field="budget",
                value=None,
                confidence=0.0,
                abstained=True,
                reason="INSUFFICIENT_EVIDENCE",
            )
        )
    else:
        facts.append(_fact("budget", budget, budget_chunks, confidence=0.96))

    currency_pairs = _collect_labeled(chunks, _CURRENCY_RE)
    if not currency_pairs and currency_from_amount:
        currency_pairs = [(currency_from_amount, chunks[0])] if chunks else []
        if amount_chunks:
            currency_pairs = [(currency_from_amount, amount_chunks[0])]
    if not currency_pairs:
        iso = _collect_labeled(chunks, _ISO_CURRENCY_RE)
        currency_pairs = iso
    currency, currency_chunks, currency_conflict = _unique_or_conflict(
        currency_pairs, field="currency", normalize=lambda v: "USD" if v == "$" else v.upper()
    )
    if currency_conflict:
        conflicts.append(currency_conflict)
        missing.append("currency")
    elif currency is None:
        missing.append("currency")
        facts.append(
            ExtractedFact(
                field="currency",
                value=None,
                confidence=0.0,
                abstained=True,
                reason="INSUFFICIENT_EVIDENCE",
            )
        )
    else:
        facts.append(_fact("currency", currency.upper(), currency_chunks, confidence=0.97))

    for field, pattern, confidence in (
        ("process_request_id", _PR_ID_RE, 0.99),
        ("requester", _REQUESTER_RE, 0.93),
        ("department", _DEPARTMENT_RE, 0.9),
        ("vendor", _VENDOR_RE, 0.9),
        ("quantity", _QTY_RE, 0.92),
        ("item_description", _ITEM_RE, 0.85),
        ("purchase_order_number", _PO_RE, 0.9),
        ("approver", _APPROVER_RE, 0.88),
        ("justification", _JUSTIFICATION_RE, 0.82),
    ):
        pairs = _collect_labeled(chunks, pattern)
        value, value_chunks, conflict = _unique_or_conflict(pairs, field=field)
        if conflict:
            conflicts.append(conflict)
            missing.append(field)
            continue
        if value is None:
            if field in {"process_request_id", "requester"}:
                missing.append(field)
                facts.append(
                    ExtractedFact(
                        field=field,
                        value=None,
                        confidence=0.0,
                        abstained=True,
                        reason="INSUFFICIENT_EVIDENCE",
                    )
                )
            continue
        lowered = value.strip().lower()
        if lowered in _FORBIDDEN_DEFAULTS:
            continue
        facts.append(_fact(field, value, value_chunks, confidence=confidence))

    quote_count_pairs = _collect_labeled(chunks, _QUOTE_COUNT_RE)
    quote_ids = _collect_labeled(chunks, _QUOTE_ID_RE)
    if quote_count_pairs:
        count, count_chunks, count_conflict = _unique_or_conflict(quote_count_pairs, field="quotation_count")
        if count_conflict:
            conflicts.append(count_conflict)
            missing.append("quotation_count")
        elif count is not None:
            facts.append(_fact("quotation_count", int(count), count_chunks, confidence=0.94))
    elif quote_ids:
        unique_ids = sorted({value.upper() for value, _ in quote_ids})
        facts.append(
            _fact(
                "quotation_count",
                len(unique_ids),
                [chunk for _, chunk in quote_ids],
                confidence=0.8,
            )
        )
        facts.append(
            _fact(
                "quotation_references",
                unique_ids,
                [chunk for _, chunk in quote_ids],
                confidence=0.8,
            )
        )
    else:
        missing.append("quotation_count")
        facts.append(
            ExtractedFact(
                field="quotation_count",
                value=None,
                confidence=0.0,
                abstained=True,
                reason="INSUFFICIENT_EVIDENCE",
            )
        )

    if budget_currency and not any(f.field == "currency" and f.value for f in facts):
        pass

    policy_pairs = _collect_labeled(chunks, _POLICY_REF_RE)
    policy_refs = [_pointer(chunk) for _, chunk in policy_pairs]

    for fact in facts:
        if (
            fact.field in {"amount", "currency", "budget", "requester"}
            and not fact.abstained
            and fact.confidence < CRITICAL_LOW_CONFIDENCE
        ):
            fact.abstained = True
            fact.value = None
            fact.reason = "LOW_CONFIDENCE"
            missing.append(fact.field)

    status: DiscoveryStatus = "OK"
    if conflicts:
        status = "DISCOVERY_CONFLICT"
    elif any(f.abstained for f in facts if f.field in {"amount", "currency"}):
        status = "INSUFFICIENT_EVIDENCE"

    return ProcurementExtraction(
        status=status,
        facts=facts,
        conflicts=conflicts,
        missing=sorted(set(missing)),
        policy_refs=policy_refs,
    )


def fact_map(extraction: ProcurementExtraction) -> dict[str, ExtractedFact]:
    return {fact.field: fact for fact in extraction.facts if not fact.abstained and fact.value is not None}
