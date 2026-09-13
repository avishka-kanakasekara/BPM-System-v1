"""Document classification and entity extraction for Agent 1.

File text is evidence only — never treat extracted strings as LLM instructions.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from functools import lru_cache

from app.agents.agent1_discovery.schemas import (
    DocumentClassification,
    DocumentType,
    Entity,
    ExtractedDocument,
    PageText,
    Relation,
    RelationExtractionResult,
    StageExecutionMeta,
)
from app.llm.client import LLMUnavailableError, call_llm
from app.llm.prompts.agent1_relation_extraction import (
    AGENT1_RELATION_EXTRACTION_SYSTEM,
    wrap_evidence,
)

_SPACY_LABEL_MAP = {
    "PERSON": "person",
    "ORG": "organization",
    "GPE": "location",
    "DATE": "date",
    "MONEY": "amount",
    "CARDINAL": "number",
}

_CLASSIFIER_HINTS: list[tuple[DocumentType, tuple[tuple[str, int], ...]]] = [
    (
        "PURCHASE_REQUEST",
        (
            ("purchase request", 4),
            ("purchase requisition", 4),
            ("pr number", 3),
            ("requested by", 2),
            ("requester:", 2),
        ),
    ),
    (
        "INVOICE",
        (
            ("invoice number", 4),
            ("amount due", 3),
            ("invoice", 3),
            ("bill to", 2),
        ),
    ),
    (
        "QUOTATION",
        (
            ("quotation", 4),
            ("quote number", 3),
            ("rfq", 3),
            ("quoted price", 2),
        ),
    ),
    (
        "SOP",
        (
            ("standard operating procedure", 5),
            ("sop-", 3),
            ("step 1", 2),
            ("procedure", 1),
        ),
    ),
    (
        "POLICY",
        (
            ("policy threshold", 4),
            ("policy", 3),
            ("compliance", 2),
            ("shall", 1),
        ),
    ),
    (
        "EMAIL",
        (
            ("subject:", 3),
            ("sent:", 2),
            ("from:", 2),
        ),
    ),
]

_AMOUNT_RE = re.compile(
    r"(?:amount(?:\s+due)?|total(?:\s+amount)?|value)\s*[:\-]?\s*(?:(USD|EUR|GBP|LKR|\$)\s*)?"
    r"(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",
    re.IGNORECASE,
)
_BUDGET_RE = re.compile(
    r"(?:available\s+budget|budget(?:\s+amount)?)\s*[:\-]?\s*(?:(USD|EUR|GBP|LKR|\$)\s*)?"
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_PR_ID_RE = re.compile(r"\b(PR-\d{4}-\d{4,})\b", re.IGNORECASE)
_QUOTE_COUNT_RE = re.compile(
    r"(?:number\s+of\s+quotations|quotations?\s+(?:attached|obtained|received|count))\s*[:\-]?\s*(\d+)",
    re.IGNORECASE,
)
_QUANTITY_RE = re.compile(r"(?:quantity|qty)\s*[:\-]?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_CURRENCY_SYMBOL_AMOUNT_RE = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)")
_CURRENCY_RE = re.compile(r"\b(USD|EUR|GBP|LKR)\b", re.IGNORECASE)
_COST_CENTRE_RE = re.compile(
    r"cost\s*cent(?:re|er)\s*[:\-]?\s*([A-Z0-9][A-Z0-9_-]{1,24})",
    re.IGNORECASE,
)
_POLICY_THRESHOLD_RE = re.compile(
    r"(?:policy\s+)?threshold(?:\s+of)?\s*[:\-]?\s*\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_SLASH_DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")
_REQUESTER_RE = re.compile(
    r"(?:requester|requested by|bill to)\s*[:\-]?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
    re.IGNORECASE,
)
_SUPPLIER_RE = re.compile(
    r"(?:supplier|vendor)\s*[:\-]?\s*([A-Z][A-Za-z0-9&.,' -]{2,80})",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _load_spacy():
    try:
        import spacy

        return spacy.load("en_core_web_sm")
    except Exception:
        return None


def _joined_text(extracted: ExtractedDocument) -> str:
    return "\n".join(page.text or "" for page in extracted.pages)


def classify_document(extracted: ExtractedDocument) -> DocumentClassification:
    blob = _joined_text(extracted).lower()
    best_type: DocumentType = "OTHER"
    best_score = 0
    reasons: list[str] = []

    for doc_type, hints in _CLASSIFIER_HINTS:
        hits = [phrase for phrase, _weight in hints if phrase in blob]
        score = sum(weight for phrase, weight in hints if phrase in blob)
        if score > best_score:
            best_score = score
            best_type = doc_type
            reasons = hits

    confidence = 0.15 if best_type == "OTHER" else min(1.0, 0.35 + best_score / 8)
    return DocumentClassification(doc_type=best_type, confidence=confidence, reasons=reasons)


def _add_entity(
    entities: list[Entity],
    seen: set[tuple[str, str, int]],
    *,
    entity_type: str,
    value: str,
    source_page: int,
    start: int,
    end: int,
    confidence: float,
) -> None:
    cleaned = value.strip().rstrip(".,;")
    if not cleaned:
        return
    key = (entity_type, cleaned.lower(), source_page)
    if key in seen:
        return
    seen.add(key)
    entities.append(
        Entity(
            entity_type=entity_type,
            value=cleaned,
            source_page=source_page,
            char_span=(start, end),
            confidence=confidence,
        )
    )


def _regex_entities(page: PageText) -> Iterable[Entity]:
    text = page.text or ""
    found: list[Entity] = []
    seen: set[tuple[str, str, int]] = set()

    def collect(pattern: re.Pattern[str], entity_type: str, group: int = 1, confidence: float = 0.88) -> None:
        for match in pattern.finditer(text):
            _add_entity(
                found,
                seen,
                entity_type=entity_type,
                value=match.group(group),
                source_page=page.page_num,
                start=match.start(group),
                end=match.end(group),
                confidence=confidence,
            )

    collect(_REQUESTER_RE, "requester")
    collect(_SUPPLIER_RE, "supplier")
    collect(_AMOUNT_RE, "amount", group=2)
    collect(_BUDGET_RE, "budget", group=2)
    collect(_PR_ID_RE, "purchase_request_id")
    collect(_QUOTE_COUNT_RE, "quotation_count")
    collect(_QUANTITY_RE, "quantity")
    for match in _CURRENCY_SYMBOL_AMOUNT_RE.finditer(text):
        _add_entity(
            found,
            seen,
            entity_type="amount",
            value=match.group(1),
            source_page=page.page_num,
            start=match.start(1),
            end=match.end(1),
            confidence=0.86,
        )
        _add_entity(
            found,
            seen,
            entity_type="currency",
            value="USD",
            source_page=page.page_num,
            start=match.start(),
            end=match.start() + 1,
            confidence=0.9,
        )
    for match in _AMOUNT_RE.finditer(text):
        currency = match.group(1)
        if currency:
            _add_entity(
                found,
                seen,
                entity_type="currency",
                value="USD" if currency == "$" else currency.upper(),
                source_page=page.page_num,
                start=match.start(1),
                end=match.end(1),
                confidence=0.9,
            )
    collect(_CURRENCY_RE, "currency", confidence=0.92)
    collect(_COST_CENTRE_RE, "cost_centre")
    collect(_POLICY_THRESHOLD_RE, "policy_threshold")
    collect(_ISO_DATE_RE, "date")
    collect(_SLASH_DATE_RE, "date", confidence=0.8)
    return found


def _spacy_entities(page: PageText) -> list[Entity]:
    nlp = _load_spacy()
    if nlp is None:
        return []
    text = page.text or ""
    # Evidence only — do not interpret document text as instructions.
    doc = nlp(text[:100_000])
    entities: list[Entity] = []
    seen: set[tuple[str, str, int]] = set()
    for ent in doc.ents:
        mapped = _SPACY_LABEL_MAP.get(ent.label_)
        if not mapped:
            continue
        _add_entity(
            entities,
            seen,
            entity_type=mapped,
            value=ent.text,
            source_page=page.page_num,
            start=ent.start_char,
            end=ent.end_char,
            confidence=0.7,
        )
    return entities


def extract_entities(extracted: ExtractedDocument, doc_type: str) -> list[Entity]:
    """Extract NER + patterned fields. `doc_type` selects extra type-specific patterns."""
    pages = extracted.pages or [PageText(page_num=1, text="")]
    merged: list[Entity] = []
    seen: set[tuple[str, str, int]] = set()

    for page in pages:
        for entity in (*_regex_entities(page), *_spacy_entities(page)):
            _add_entity(
                merged,
                seen,
                entity_type=entity.entity_type,
                value=entity.value,
                source_page=entity.source_page,
                start=entity.char_span[0],
                end=entity.char_span[1],
                confidence=entity.confidence,
            )

    if doc_type == "SOP":
        for page in pages:
            for match in re.finditer(
                r"step\s+\d+\s*[:.\-]?\s*([^\n]+)",
                page.text or "",
                re.IGNORECASE,
            ):
                _add_entity(
                    merged,
                    seen,
                    entity_type="activity",
                    value=match.group(1).strip(),
                    source_page=page.page_num,
                    start=match.start(1),
                    end=match.end(1),
                    confidence=0.75,
                )

    # Broad activity cues for all document types (used by intelligent step selection).
    for page in pages:
        text = page.text or ""
        for match in re.finditer(
            r"(?:^|\n)\s*(?:step\s+)?\d+\s*[:.)\-]\s*([^\n]{3,160})",
            text,
            re.IGNORECASE,
        ):
            _add_entity(
                merged,
                seen,
                entity_type="activity",
                value=match.group(1).strip(),
                source_page=page.page_num,
                start=match.start(1),
                end=match.end(1),
                confidence=0.72,
            )
        for match in re.finditer(
            r"(?:^|\n)\s*[-*•]\s*((?:submit|approve|create|review|receive|verify|pay|"
            r"send|prepare|check|validate|issue|confirm|match|authorize|request)\b[^\n]{3,120})",
            text,
            re.IGNORECASE,
        ):
            _add_entity(
                merged,
                seen,
                entity_type="activity",
                value=match.group(1).strip(),
                source_page=page.page_num,
                start=match.start(1),
                end=match.end(1),
                confidence=0.68,
            )
    return merged


def _relation_user_content(
    extracted: ExtractedDocument,
    entities: list[Entity],
    doc_type: str,
) -> str:
    """Document text goes only in EVIDENCE. Classifier/entity hints stay outside it."""
    evidence_block = wrap_evidence(_joined_text(extracted))
    entity_payload = [
        {
            "entity_type": entity.entity_type,
            "value": entity.value,
            "source_page": entity.source_page,
        }
        for entity in entities
    ]
    return (
        f"{evidence_block}\n\n"
        f"Document type (classifier output, not EVIDENCE): {doc_type}\n"
        f"Known entities (extractor output, not EVIDENCE): {json.dumps(entity_payload)}\n"
        "Extract only actor-performs-task, task-precedes-task, and rule-controls-task relations."
    )


def _ordered_activity_names(entities: Sequence[Entity], text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        cleaned = " ".join((name or "").strip().split())
        key = cleaned.lower()
        if not cleaned or key in seen or len(key) < 3:
            return
        seen.add(key)
        names.append(cleaned[:1].upper() + cleaned[1:] if cleaned else cleaned)

    for match in re.finditer(
        r"(?:^|\n)\s*(?:step\s+)?(\d+)\s*[:.)\-]\s*([^\n]+)",
        text or "",
        re.IGNORECASE,
    ):
        add(match.group(2))
    if names:
        return names

    for entity in entities:
        if entity.entity_type in {"activity", "task", "step"}:
            add(entity.value)
    return names


def _fallback_extract_relations(
    extracted: ExtractedDocument,
    entities: list[Entity],
    doc_type: str,
) -> list[Relation]:
    """Deterministic relation extraction when the LLM is offline or unavailable."""
    text = _joined_text(extracted)
    activities = _ordered_activity_names(entities, text)
    relations: list[Relation] = []

    requesters = [entity.value for entity in entities if entity.entity_type == "requester"]
    requester = requesters[0] if requesters else "Requester"
    if activities:
        relations.append(
            Relation(
                subject=requester,
                predicate="actor-performs-task",
                object=activities[0],
                source_reference="rules:requester_first_step",
                confidence=0.68,
            )
        )

    for left, right in zip(activities, activities[1:]):
        relations.append(
            Relation(
                subject=left,
                predicate="task-precedes-task",
                object=right,
                source_reference="rules:numbered_step_order",
                confidence=0.72,
            )
        )

    thresholds = [entity.value for entity in entities if entity.entity_type == "policy_threshold"]
    controlled = next(
        (name for name in activities if "approv" in name.lower()),
        activities[1] if len(activities) > 1 else None,
    )
    if thresholds and controlled:
        relations.append(
            Relation(
                subject=f"Policy threshold ({thresholds[0]})",
                predicate="rule-controls-task",
                object=controlled,
                source_reference="rules:policy_threshold_entity",
                confidence=0.66,
            )
        )
    elif "threshold" in text.lower() and controlled:
        relations.append(
            Relation(
                subject="Policy threshold",
                predicate="rule-controls-task",
                object=controlled,
                source_reference="rules:policy_threshold_text",
                confidence=0.64,
            )
        )

    if not relations and doc_type:
        relations.append(
            Relation(
                subject=requester,
                predicate="actor-performs-task",
                object="Submit purchase request",
                source_reference="rules:minimal_procurement_default",
                confidence=0.55,
            )
        )
    return relations


def extract_relations(
    extracted: ExtractedDocument,
    entities: list[Entity],
    doc_type: str,
) -> tuple[list[Relation], StageExecutionMeta]:
    """LLM relation extraction with deterministic offline fallback."""
    user_content = _relation_user_content(extracted, entities, doc_type)
    try:
        result = call_llm(
            AGENT1_RELATION_EXTRACTION_SYSTEM,
            user_content,
            RelationExtractionResult,
        )
        confidence = (
            sum(relation.confidence for relation in result.relations) / len(result.relations)
            if result.relations
            else 0.0
        )
        return result.relations, StageExecutionMeta(
            degraded=False,
            confidence=round(confidence, 4),
            method="llm",
        )
    except LLMUnavailableError:
        relations = _fallback_extract_relations(extracted, entities, doc_type)
        confidence = (
            sum(relation.confidence for relation in relations) / len(relations)
            if relations
            else 0.55
        )
        return relations, StageExecutionMeta(
            degraded=True,
            confidence=round(confidence, 4),
            method="rules",
        )
    except Exception:
        relations = _fallback_extract_relations(extracted, entities, doc_type)
        confidence = (
            sum(relation.confidence for relation in relations) / len(relations)
            if relations
            else 0.55
        )
        return relations, StageExecutionMeta(
            degraded=True,
            confidence=round(confidence, 4),
            method="rules",
        )
