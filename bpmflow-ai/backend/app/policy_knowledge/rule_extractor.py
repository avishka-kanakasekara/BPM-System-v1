"""Deterministic policy text chunking and structured rule extraction.

No LLM guesses. Explicit rules win; text patterns only extract clearly
stated numeric thresholds and evidence lists.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from .constants import PolicyOperator, PolicyRuleType
from .schemas import PolicyChunk, PolicyRule

_AMOUNT_RE = re.compile(
    r"(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?P<currency>LKR|USD|EUR|GBP)?",
    re.IGNORECASE,
)

_THRESHOLD_PATTERNS: list[tuple[re.Pattern[str], PolicyRuleType]] = [
    (
        re.compile(
            r"(?:purchases?|amounts?|spend|orders?)\s+(?:above|over|exceeding|greater than)\s+"
            r"(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?P<currency>LKR|USD|EUR|GBP)?",
            re.IGNORECASE,
        ),
        PolicyRuleType.APPROVAL_THRESHOLD,
    ),
    (
        re.compile(
            r"(?:high[- ]value|approval)\s+(?:threshold|limit)\s*(?:of|is|=|:)?\s*"
            r"(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?P<currency>LKR|USD|EUR|GBP)?",
            re.IGNORECASE,
        ),
        PolicyRuleType.HIGH_VALUE_THRESHOLD,
    ),
]

_EVIDENCE_RE = re.compile(
    r"(?:require[sd]?|must\s+include|mandatory)\s+(?:a\s+)?(?P<item>quotation|quote|invoice|po|purchase\s+order|receipt|spec)",
    re.IGNORECASE,
)

_APPROVAL_ROLE_RE = re.compile(
    r"require[sd]?\s+(?P<role>senior\s+management|manager|finance|cfo|director)\s+approval",
    re.IGNORECASE,
)

# Requester authorization only — not the same as "require X approval" (approver).
_REQUESTER_AUTHORIZATION_RE = re.compile(
    r"(?:only|must\s+be)\s+(?P<role>senior\s+management|manager|finance|cfo|director|"
    r"finance\s+officer|procurement\s+officer)s?\s+(?:may|can|are\s+authorized\s+to|"
    r"is\s+authorized\s+to)\s+(?:submit|create|initiate|request)",
    re.IGNORECASE,
)

_SLA_RE = re.compile(
    r"(?:sla|deadline|must\s+complete)\s*(?:within|=|:)?\s*(?P<hours>\d+(?:\.\d+)?)\s*hours?",
    re.IGNORECASE,
)


def _parse_amount(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def chunk_text(text: str, *, max_chars: int = 900) -> list[PolicyChunk]:
    """Split policy text into overlapping retrieval chunks."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]
    if not paragraphs:
        paragraphs = [cleaned]

    chunks: list[PolicyChunk] = []
    buffer = ""
    section = None
    index = 0
    page = 1

    for paragraph in paragraphs:
        heading = None
        if len(paragraph) < 120 and not paragraph.endswith("."):
            heading = paragraph
        piece = paragraph if not buffer else f"{buffer}\n\n{paragraph}"
        if len(piece) <= max_chars:
            buffer = piece
            if heading:
                section = heading
            continue
        if buffer:
            chunks.append(
                PolicyChunk(
                    id=uuid4(),
                    chunk_index=index,
                    page_number=page,
                    section_title=section,
                    text_content=buffer,
                )
            )
            index += 1
            page += 1
        buffer = paragraph
        if heading:
            section = heading

    if buffer:
        chunks.append(
            PolicyChunk(
                id=uuid4(),
                chunk_index=index,
                page_number=page,
                section_title=section,
                text_content=buffer,
            )
        )
    return chunks


def extract_rules_from_text(text: str) -> list[PolicyRule]:
    """Extract explicit numeric/evidence rules from policy text without LLM."""
    rules: list[PolicyRule] = []
    seen: set[tuple] = set()

    for pattern, rule_type in _THRESHOLD_PATTERNS:
        for match in pattern.finditer(text or ""):
            amount = _parse_amount(match.group("amount"))
            if amount is None:
                continue
            currency = match.groupdict().get("currency")
            currency = currency.upper() if currency else None
            key = (rule_type.value, str(amount), currency)
            if key in seen:
                continue
            seen.add(key)
            role_match = _APPROVAL_ROLE_RE.search(match.string[match.start() : match.end() + 80])
            rules.append(
                PolicyRule(
                    rule_type=rule_type,
                    operator=PolicyOperator.GT,
                    threshold_value=amount,
                    currency=currency,
                    required_approval=(
                        role_match.group("role").upper().replace(" ", "_")
                        if role_match
                        else "SENIOR_MANAGEMENT"
                        if rule_type is PolicyRuleType.APPROVAL_THRESHOLD
                        else None
                    ),
                    description=match.group(0).strip(),
                )
            )

    evidence_items: list[str] = []
    for match in _EVIDENCE_RE.finditer(text or ""):
        item = re.sub(r"\s+", "_", match.group("item").strip().lower())
        if item == "quote":
            item = "quotation"
        if item == "purchase_order":
            item = "po"
        if item not in evidence_items:
            evidence_items.append(item)
    if evidence_items:
        rules.append(
            PolicyRule(
                rule_type=PolicyRuleType.REQUIRED_EVIDENCE,
                required_evidence=evidence_items,
                description="Required evidence listed in policy text",
            )
        )

    # "require Senior Management approval" is an *approver* requirement for
    # threshold breaches (captured on APPROVAL_THRESHOLD.required_approval).
    # Do not treat it as a requester role gate — that caused below-threshold
    # purchases to be BLOCK_ACTION'd incorrectly.
    for match in _REQUESTER_AUTHORIZATION_RE.finditer(text or ""):
        role = match.group("role").upper().replace(" ", "_")
        rules.append(
            PolicyRule(
                rule_type=PolicyRuleType.REQUIRED_AUTHORIZATION,
                required_roles=[role],
                required_approval=role,
                description=match.group(0).strip(),
            )
        )

    for match in _SLA_RE.finditer(text or ""):
        hours = _parse_amount(match.group("hours"))
        if hours is None:
            continue
        rules.append(
            PolicyRule(
                rule_type=PolicyRuleType.SLA,
                sla_hours=hours,
                description=match.group(0).strip(),
            )
        )

    # SoD is assumed for procurement/approval policies unless explicitly waived.
    if re.search(r"segregation of duties|requester cannot approve", text or "", re.I):
        rules.append(
            PolicyRule(
                rule_type=PolicyRuleType.SEGREGATION_OF_DUTIES,
                description="Segregation of duties required by policy",
            )
        )

    return rules
