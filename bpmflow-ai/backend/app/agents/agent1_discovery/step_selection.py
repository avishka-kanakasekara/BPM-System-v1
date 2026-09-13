"""Intelligent process-step selection for Agent 1.

Analyses document evidence (plus extractor hints) and returns the ordered
steps required for THIS process. Prefers LLM selection; falls back to
deterministic heuristics when the LLM is unavailable or returns empty.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from app.agents.agent1_discovery.schemas import (
    DiscoveredStep,
    Entity,
    ExtractedDocument,
    RejectedStepCandidate,
    Relation,
    StageExecutionMeta,
    StepSelectionResult,
)
from app.core.logging import get_logger
from app.llm.client import LLMUnavailableError, call_llm
from app.llm.prompts.agent1_step_selection import (
    AGENT1_STEP_SELECTION_SYSTEM,
    build_step_selection_user_content,
)

logger = get_logger(__name__)

_NUMBERED_STEP_RE = re.compile(
    r"(?:^|\n)\s*(?:step\s+)?(\d+)\s*[:.)\-]\s*([^\n]+)",
    re.IGNORECASE,
)
_BULLET_ACTION_RE = re.compile(
    r"(?:^|\n)\s*[-*•]\s*((?:submit|approve|create|review|receive|verify|pay|"
    r"send|prepare|check|validate|issue|confirm|match|authorize|request)\b[^\n]{3,120})",
    re.IGNORECASE,
)


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _title_case_step(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", (name or "").strip(" .-:\t"))
    if not cleaned:
        return cleaned
    # Keep short acronyms; otherwise title-case words.
    parts = []
    for token in cleaned.split(" "):
        if token.isupper() and len(token) <= 4:
            parts.append(token)
        else:
            parts.append(token[:1].upper() + token[1:])
    return " ".join(parts)


def _joined_document_text(documents: Sequence[ExtractedDocument]) -> str:
    chunks: list[str] = []
    for doc in documents:
        for page in doc.pages or []:
            text = (page.text or "").strip()
            if text:
                chunks.append(f"[page {page.page_num}]\n{text}")
    return "\n\n".join(chunks)


def _activity_candidates_from_entities(entities: Sequence[Entity]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for entity in entities:
        if entity.entity_type not in {"activity", "task", "step"}:
            continue
        key = _norm(entity.value)
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(_title_case_step(entity.value))
    return names


def _activity_candidates_from_relations(relations: Sequence[Relation]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for relation in relations:
        candidates: list[str] = []
        if relation.predicate == "actor-performs-task":
            candidates.append(relation.object)
        elif relation.predicate == "task-precedes-task":
            candidates.extend([relation.subject, relation.object])
        elif relation.predicate == "rule-controls-task":
            candidates.append(relation.object)
        for name in candidates:
            key = _norm(name)
            if not key or key in seen:
                continue
            seen.add(key)
            names.append(_title_case_step(name))
    return names


def _heuristic_steps_from_text(text: str) -> list[DiscoveredStep]:
    steps: list[DiscoveredStep] = []
    seen: set[str] = set()
    order = 1
    for match in _NUMBERED_STEP_RE.finditer(text or ""):
        name = _title_case_step(match.group(2))
        key = _norm(name)
        if not key or key in seen or len(key) < 3:
            continue
        seen.add(key)
        steps.append(
            DiscoveredStep(
                name=name,
                order=order,
                required=True,
                rationale="Numbered step found in document text.",
                source_reference=f"step {match.group(1)}",
                confidence=0.78,
            )
        )
        order += 1
    if steps:
        return steps

    for match in _BULLET_ACTION_RE.finditer(text or ""):
        name = _title_case_step(match.group(1))
        key = _norm(name)
        if not key or key in seen:
            continue
        seen.add(key)
        steps.append(
            DiscoveredStep(
                name=name,
                order=order,
                required=True,
                rationale="Actionable bullet found in document text.",
                source_reference="bullet list",
                confidence=0.7,
            )
        )
        order += 1
    return steps


def _heuristic_from_hints(
    known_activities: Sequence[str],
    relations: Sequence[Relation],
) -> list[DiscoveredStep]:
    # Prefer precedes-chain order when available.
    successors: dict[str, str] = {}
    predecessors: set[str] = set()
    nodes: set[str] = set()
    for relation in relations:
        if relation.predicate != "task-precedes-task":
            continue
        left = _title_case_step(relation.subject)
        right = _title_case_step(relation.object)
        if not left or not right:
            continue
        successors[_norm(left)] = right
        predecessors.add(_norm(right))
        nodes.add(_norm(left))
        nodes.add(_norm(right))

    ordered: list[str] = []
    if nodes:
        starts = [n for n in nodes if n not in predecessors]
        cursor = starts[0] if starts else next(iter(nodes))
        seen: set[str] = set()
        while cursor and cursor not in seen:
            seen.add(cursor)
            # recover display name
            display = next(
                (a for a in known_activities if _norm(a) == cursor),
                cursor.title(),
            )
            for relation in relations:
                if relation.predicate == "task-precedes-task" and _norm(relation.subject) == cursor:
                    display = _title_case_step(relation.subject)
                    break
                if relation.predicate == "task-precedes-task" and _norm(relation.object) == cursor:
                    display = _title_case_step(relation.object)
            ordered.append(display)
            nxt = successors.get(cursor)
            cursor = _norm(nxt) if nxt else ""

    if not ordered:
        ordered = list(known_activities)

    return [
        DiscoveredStep(
            name=name,
            order=index,
            required=True,
            rationale="Derived from extractor activity/relation hints.",
            source_reference="extractor_hints",
            confidence=0.72,
        )
        for index, name in enumerate(ordered, start=1)
    ]


def _dedupe_steps(steps: Iterable[DiscoveredStep]) -> list[DiscoveredStep]:
    cleaned: list[DiscoveredStep] = []
    seen: set[str] = set()
    for step in sorted(steps, key=lambda item: item.order):
        if not step.required:
            continue
        key = _norm(step.name)
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(
            step.model_copy(
                update={
                    "name": _title_case_step(step.name),
                    "order": len(cleaned) + 1,
                }
            )
        )
    return cleaned


def select_process_steps(
    documents: Sequence[ExtractedDocument],
    entities: Sequence[Entity],
    relations: Sequence[Relation],
    *,
    doc_types: Sequence[str] | None = None,
) -> tuple[StepSelectionResult, StageExecutionMeta]:
    """Analyse evidence and select the ordered steps required for this process."""
    text = _joined_document_text(documents)
    known = _activity_candidates_from_entities(entities)
    for name in _activity_candidates_from_relations(relations):
        if _norm(name) not in {_norm(item) for item in known}:
            known.append(name)

    relation_hints = [
        {
            "subject": relation.subject,
            "predicate": relation.predicate,
            "object": relation.object,
            "confidence": relation.confidence,
        }
        for relation in relations
    ]
    types = list(doc_types or [])

    result: StepSelectionResult | None = None
    llm_unavailable = False
    if text.strip() or known:
        try:
            result = call_llm(
                AGENT1_STEP_SELECTION_SYSTEM,
                build_step_selection_user_content(
                    text,
                    doc_types=types,
                    known_activities=known,
                    relation_hints=relation_hints,
                ),
                StepSelectionResult,
            )
        except LLMUnavailableError:
            llm_unavailable = True
        except Exception:
            logger.exception("agent1_step_selection_llm_failed")
            result = None

    if result is not None and result.steps:
        steps = _dedupe_steps(result.steps)
        if steps:
            logger.info(
                "agent1_step_selection_complete",
                extra={
                    "source": "llm",
                    "step_count": len(steps),
                    "rejected_count": len(result.rejected_candidates),
                },
            )
            confidence = _mean([step.confidence for step in steps])
            return (
                StepSelectionResult(
                    process_name=result.process_name,
                    steps=steps,
                    rejected_candidates=result.rejected_candidates,
                    selection_summary=result.selection_summary
                    or "LLM selected required steps from document evidence.",
                ),
                StageExecutionMeta(degraded=False, confidence=confidence, method="llm"),
            )

    heuristic_text_steps = _heuristic_steps_from_text(text)
    if heuristic_text_steps:
        steps = _dedupe_steps(heuristic_text_steps)
        logger.info(
            "agent1_step_selection_complete",
            extra={"source": "text_heuristic", "step_count": len(steps)},
        )
        confidence = _mean([step.confidence for step in steps])
        return (
            StepSelectionResult(
                process_name=None,
                steps=steps,
                rejected_candidates=[],
                selection_summary="Selected numbered/actionable steps found in the document text.",
            ),
            StageExecutionMeta(degraded=True, confidence=confidence, method="text_heuristic"),
        )

    hint_steps = _heuristic_from_hints(known, relations)
    steps = _dedupe_steps(hint_steps)
    rejected = [
        RejectedStepCandidate(
            name="Generic happy-path template",
            reason="No document-supported steps were available; avoided inventing a fixed template.",
        )
    ]
    logger.info(
        "agent1_step_selection_complete",
        extra={"source": "hint_heuristic", "step_count": len(steps)},
    )
    confidence = _mean([step.confidence for step in steps]) if steps else 0.55
    return (
        StepSelectionResult(
            process_name=None,
            steps=steps,
            rejected_candidates=rejected if not steps else [],
            selection_summary=(
                "Selected steps from extractor activity and relation hints."
                if steps
                else "No required steps could be selected from the available evidence."
            ),
        ),
        StageExecutionMeta(
            degraded=True,
            confidence=confidence,
            method="hint_heuristic" if llm_unavailable else "rules",
        ),
    )


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)
