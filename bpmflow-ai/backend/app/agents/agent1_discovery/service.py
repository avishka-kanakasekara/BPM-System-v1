"""Assemble Agent 1 outputs into a ProcessJSON document.

Never invent values: if evidence is missing or contradictory, record the field
in `missing_or_contradictory_fields` and leave it empty.
"""

from __future__ import annotations

import re
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.agent1_discovery.document_parser import (
    extract_text,
    sanitize_filename,
    validate_and_ingest,
)
from app.agents.agent1_discovery.extractors import (
    classify_document,
    extract_entities,
    extract_relations,
)
from app.agents.agent1_discovery.ingest import content_sha256, ingest_extracted
from app.agents.agent1_discovery.persistence import persist_discovery
from app.agents.agent1_discovery.process_mining import analyze_event_log
from app.agents.agent1_discovery.schemas import (
    Entity,
    ExtractedDocument,
    ProcessActivity,
    ProcessDependency,
    ProcessException,
    ProcessJSON,
    ProcessMiningResult,
    ProcessRule,
    Relation,
    StageExecutionMeta,
    StepSelectionResult,
)
from app.agents.agent1_discovery.step_selection import select_process_steps
from app.agents.agent4_orchestrator.risk_facts import RiskFacts, validate_risk_facts
from app.core.logging import get_logger
from app.ir.corpus import get_document_corpus
from app.schemas.agent_message import AgentMessageStatus, DiscoveryAgentMessage, EvidenceReference

logger = get_logger(__name__)


def _norm(value: str) -> str:
    return " ".join((value or "").lower().split())


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _unique_or_conflict(values: list[str]) -> tuple[str | None, bool]:
    unique = []
    seen: set[str] = set()
    for value in values:
        key = _norm(value)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(value.strip())
    if len(unique) == 1:
        return unique[0], False
    if len(unique) > 1:
        return None, True
    return None, False


def _lookup_duration(activity: str, waiting: dict[str, float]) -> float | None:
    if activity in waiting:
        return waiting[activity]
    wanted = _norm(activity)
    for name, hours in waiting.items():
        if _norm(name) == wanted:
            return hours
    return None


def _lookup_count(activity: str, counts: dict[str, int]) -> int | None:
    if not counts:
        return None
    if activity in counts:
        return counts[activity]
    wanted = _norm(activity)
    for name, value in counts.items():
        if _norm(name) == wanted:
            return value
    return None


_DURATION_HINT_RE = re.compile(
    r"(?P<activity>.+?)\s+(?:takes?|typically|usually|about|around|within)\s+"
    r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>minutes?|mins?|hours?|hrs?|days?|weeks?)",
    flags=re.IGNORECASE,
)


def _hours_from_amount_unit(amount: float, unit: str) -> float:
    u = unit.lower()
    if u.startswith("min"):
        return round(amount / 60.0, 4)
    if u.startswith("hour") or u.startswith("hr"):
        return round(amount, 4)
    if u.startswith("day"):
        return round(amount * 24.0, 4)
    if u.startswith("week"):
        return round(amount * 24.0 * 7.0, 4)
    return round(amount, 4)


def _estimated_durations_from_text(
    entities: list[Entity],
    relations: list[Relation],
) -> dict[str, tuple[float, str]]:
    """Pull explicit duration phrases from evidence text. Never invent values."""
    snippets: list[str] = []
    for entity in entities:
        if entity.value:
            snippets.append(entity.value)
    for relation in relations:
        snippets.append(
            f"{relation.subject} {relation.predicate} {relation.object}".replace("-", " ")
        )
        if relation.source_reference:
            snippets.append(relation.source_reference)

    found: dict[str, tuple[float, str]] = {}
    for snippet in snippets:
        text = " ".join(str(snippet).split())
        if not text:
            continue
        for match in _DURATION_HINT_RE.finditer(text):
            activity = match.group("activity").strip(" :-,\t")
            amount = float(match.group("amount"))
            unit = match.group("unit")
            hours = _hours_from_amount_unit(amount, unit)
            note = f"Estimated from evidence text: “{match.group(0).strip()}”"
            key = _norm(activity)
            if key and key not in found:
                found[key] = (hours, note)
    return found


def _estimate_for_activity(
    activity: str,
    estimates: dict[str, tuple[float, str]],
) -> tuple[float, str] | None:
    wanted = _norm(activity)
    if wanted in estimates:
        return estimates[wanted]
    for key, value in estimates.items():
        if key and (key in wanted or wanted in key):
            return value
    return None


def build_process_json(
    entities: list[Entity],
    relations: list[Relation],
    mining_result: ProcessMiningResult,
    step_selection: StepSelectionResult | None = None,
) -> ProcessJSON:
    missing: list[str] = []

    name_values = [
        entity.value
        for entity in entities
        if entity.entity_type in {"process", "process_name", "process_title"}
    ]
    if step_selection and step_selection.process_name:
        name_values.insert(0, step_selection.process_name)
    process_name, name_conflict = _unique_or_conflict(name_values)
    if name_conflict:
        missing.append("process_name (contradictory evidence)")
    elif process_name is None:
        missing.append("process_name")

    # Priority for required steps:
    # 1) Event-log most frequent variant (measured process mining)
    # 2) Intelligent document step selection
    # 3) Relation-derived task names
    # 4) Activity entities extracted from text
    activity_names = list(mining_result.most_frequent_variant)
    step_source = "event_log_variant" if activity_names else None
    if not activity_names and step_selection and step_selection.steps:
        activity_names = [step.name for step in step_selection.steps if step.required]
        step_source = "intelligent_document_selection"
    if not activity_names:
        from_relations: list[str] = []
        seen: set[str] = set()
        for relation in relations:
            candidates = []
            if relation.predicate == "actor-performs-task":
                candidates.append(relation.object)
            elif relation.predicate == "task-precedes-task":
                candidates.extend([relation.subject, relation.object])
            for name in candidates:
                key = _norm(name)
                if key and key not in seen:
                    seen.add(key)
                    from_relations.append(name)
        activity_names = from_relations
        if activity_names:
            step_source = "relation_hints"
    if not activity_names:
        from_entities: list[str] = []
        seen_entities: set[str] = set()
        for entity in entities:
            if entity.entity_type not in {"activity", "task", "step"}:
                continue
            key = _norm(entity.value)
            if key and key not in seen_entities:
                seen_entities.add(key)
                from_entities.append(entity.value.strip())
        activity_names = from_entities
        if activity_names:
            step_source = "activity_entities"
    if not activity_names:
        missing.append("activities")
        step_source = "none"

    actors_by_task: dict[str, list[str]] = defaultdict(list)
    rules_by_task: dict[str, list[Relation]] = defaultdict(list)
    for relation in relations:
        if relation.predicate == "actor-performs-task":
            actors_by_task[_norm(relation.object)].append(relation.subject)
        elif relation.predicate == "rule-controls-task":
            rules_by_task[_norm(relation.object)].append(relation)
    if step_selection:
        for step in step_selection.steps:
            if step.actor_hint:
                actors_by_task[_norm(step.name)].append(step.actor_hint)

    systems = [entity.value for entity in entities if entity.entity_type == "system"]
    _, system_conflict = _unique_or_conflict(systems)
    if system_conflict:
        missing.append("system (contradictory evidence)")

    text_estimates = _estimated_durations_from_text(entities, relations)
    rework_set = {_norm(name) for name in mining_result.rework_activities}
    main_path_set = {_norm(name) for name in mining_result.most_frequent_variant}
    total_cases = mining_result.total_cases

    activities: list[ProcessActivity] = []
    filled_slots = 0
    total_slots = 0
    for name in activity_names:
        key = _norm(name)
        total_slots += 5
        actor, actor_conflict = _unique_or_conflict(actors_by_task.get(key, []))
        if actor_conflict:
            missing.append(f"activities.{name}.actor (contradictory evidence)")
        elif actor is None:
            missing.append(f"activities.{name}.actor")
        else:
            filled_slots += 1

        activity_system = None
        missing.append(f"activities.{name}.system")

        duration = _lookup_duration(name, mining_result.avg_waiting_time_per_activity)
        duration_source: str | None = None
        duration_note: str | None = None
        if duration is not None:
            duration_source = "measured"
            duration_note = "Measured from event-log timestamps (average wait before this step)."
            filled_slots += 1
        else:
            estimated = _estimate_for_activity(name, text_estimates)
            if estimated is not None:
                duration, duration_note = estimated
                duration_source = "estimated_text"
                filled_slots += 1
            else:
                duration_source = "unavailable"
                duration_note = (
                    "No timestamps or explicit duration phrase found for this step."
                )
                missing.append(f"activities.{name}.avg_duration")

        controlling = rules_by_task.get(key, [])
        entry = [rel.subject for rel in controlling]
        if entry:
            filled_slots += 1
        else:
            missing.append(f"activities.{name}.entry_conditions")

        # Exit conditions are not implied by precedes/performs relations.
        missing.append(f"activities.{name}.exit_conditions")

        event_count = _lookup_count(name, mining_result.activity_event_counts)
        case_count = _lookup_count(name, mining_result.activity_case_counts)
        case_coverage = None
        if case_count is not None and total_cases > 0:
            case_coverage = round(case_count / total_cases, 4)

        activities.append(
            ProcessActivity(
                name=name,
                actor=actor,
                system=activity_system,
                avg_duration=duration,
                entry_conditions=entry,
                exit_conditions=[],
                duration_source=duration_source,
                duration_note=duration_note,
                occurrence_count=event_count,
                case_count=case_count,
                case_coverage=case_coverage,
                on_main_path=(key in main_path_set) if main_path_set else True,
                is_rework=key in rework_set,
            )
        )

    rules = [
        ProcessRule(
            description=relation.subject,
            controls_activity=relation.object,
            source_reference=relation.source_reference,
        )
        for relation in relations
        if relation.predicate == "rule-controls-task"
    ]
    if not rules:
        missing.append("rules")

    dependencies = [
        ProcessDependency(
            predecessor=relation.subject,
            successor=relation.object,
            source_reference=relation.source_reference,
        )
        for relation in relations
        if relation.predicate == "task-precedes-task"
    ]
    if not dependencies and len(activity_names) > 1:
        # Fall back to sequential order from the selected/main path when mining has a
        # variant or intelligent selection ordered the steps, but document relations
        # did not spell out precedes links.
        ordered_path = list(mining_result.most_frequent_variant)
        if not ordered_path and step_selection and step_selection.steps:
            ordered_path = [step.name for step in step_selection.steps if step.required]
        if len(ordered_path) > 1:
            for left, right in zip(ordered_path, ordered_path[1:]):
                dependencies.append(
                    ProcessDependency(
                        predecessor=left,
                        successor=right,
                        source_reference=(
                            "most_frequent_variant"
                            if mining_result.most_frequent_variant
                            else "intelligent_step_selection"
                        ),
                    )
                )
        else:
            missing.append("dependencies")

    exceptions: list[ProcessException] = []
    for activity in mining_result.rework_activities:
        exceptions.append(
            ProcessException(
                kind="rework",
                description=f"Activity '{activity}' is repeated within a case",
            )
        )
    for flag in mining_result.flagged_exceptions:
        exceptions.append(
            ProcessException(
                kind=flag.reason,
                description=(
                    f"{flag.metric}={flag.value} exceeded threshold {flag.threshold}"
                ),
                case_id=flag.case_id,
            )
        )

    fill_rate = (filled_slots / total_slots) if total_slots else 0.0
    structure_parts = [
        1.0 if activity_names else 0.0,
        1.0 if dependencies else 0.0,
        fill_rate,
    ]
    if step_selection and step_selection.steps:
        structure_parts.append(
            _mean([step.confidence for step in step_selection.steps])
        )
    confidence = {
        "entities": _mean([entity.confidence for entity in entities]),
        "relations": _mean([relation.confidence for relation in relations]),
        "process_structure": _mean(structure_parts),
        "step_selection": (
            _mean([step.confidence for step in step_selection.steps])
            if step_selection and step_selection.steps
            else 0.0
        ),
    }

    # Preserve order while dropping duplicate gap labels.
    deduped_missing: list[str] = []
    seen_missing: set[str] = set()
    for item in missing:
        if item not in seen_missing:
            seen_missing.add(item)
            deduped_missing.append(item)

    measured = sum(1 for a in activities if a.duration_source == "measured")
    estimated = sum(1 for a in activities if a.duration_source == "estimated_text")
    analytics = {
        "timing_available": bool(mining_result.timing_available),
        "total_cases": mining_result.total_cases,
        "total_events": mining_result.total_events,
        "steps_with_measured_duration": measured,
        "steps_with_estimated_duration": estimated,
        "steps_without_duration": max(len(activities) - measured - estimated, 0),
        "rework_step_count": len(mining_result.rework_activities),
        "fallback_mode": (
            "frequency_and_path"
            if not mining_result.timing_available
            else "measured_timing"
        ),
        "step_selection_source": step_source,
        "step_selection_summary": (
            step_selection.selection_summary if step_selection else None
        ),
        "selected_step_rationales": (
            [
                {
                    "name": step.name,
                    "order": step.order,
                    "rationale": step.rationale,
                    "source_reference": step.source_reference,
                    "confidence": step.confidence,
                }
                for step in step_selection.steps
            ]
            if step_selection
            else []
        ),
        "rejected_step_candidates": (
            [
                {"name": item.name, "reason": item.reason}
                for item in step_selection.rejected_candidates
            ]
            if step_selection
            else []
        ),
    }

    return ProcessJSON(
        process_name=process_name,
        activities=activities,
        rules=rules,
        dependencies=dependencies,
        exceptions=exceptions,
        missing_or_contradictory_fields=deduped_missing,
        confidence=confidence,
        analytics=analytics,
    )


class _BufferedUpload:
    def __init__(self, filename: str, content: bytes, content_type: str | None):
        self.filename = filename
        self.content_type = content_type
        self.file = BytesIO(content)
        self.content = content


def _buffer_upload(file: Any) -> _BufferedUpload:
    filename = getattr(file, "filename", None) or "upload"
    content_type = getattr(file, "content_type", None)
    content: bytes = b""
    stream = getattr(file, "file", None)
    if stream is not None:
        if hasattr(stream, "seek"):
            stream.seek(0)
        raw = stream.read()
        if isinstance(raw, bytes):
            content = raw
        elif isinstance(raw, str):
            content = raw.encode("utf-8")
        if hasattr(stream, "seek"):
            stream.seek(0)
    logger.info(
        "buffer_upload",
        extra={
            "upload_filename": filename,
            "size": len(content),
            "mime_type": content_type,
        },
    )
    return _BufferedUpload(filename, content, content_type)


def _evidence_for_entities(file_id: UUID, entities: list[Entity]) -> list[EvidenceReference]:
    refs: list[EvidenceReference] = []
    for entity in entities:
        start, end = entity.char_span
        refs.append(
            EvidenceReference(
                field=f"entity.{entity.entity_type}",
                file_id=file_id,
                page=entity.source_page,
                span_start=start,
                span_end=end,
            )
        )
    return refs


_POLICY_RETRIEVAL_QUERY = (
    "approval threshold quotation requirements budget constraints "
    "segregation of duties high-value purchase approval authority evidence requirements"
)
_UNSCOPED_TENANT = UUID("00000000-0000-0000-0000-000000000000")


def _index_extracted_document(
    *,
    tenant_id: UUID | None,
    filename: str,
    content: bytes,
    extracted: ExtractedDocument,
    document_type: str | None,
    mime_type: str | None,
) -> list[Any]:
    scoped = tenant_id or _UNSCOPED_TENANT
    _, chunks, _ = ingest_extracted(
        tenant_id=scoped,
        filename=filename,
        content_hash=content_sha256(content),
        extracted=extracted,
        document_type=document_type,
        source="upload",
        mime_type=mime_type,
        size_bytes=len(content),
        db=None,
    )
    return list(chunks)


def _document_intelligence(
    *,
    tenant_id: UUID | None,
    chunks: list[Any],
    parse_failures: list[str],
    extracted_documents: list[ExtractedDocument] | None = None,
) -> dict[str, Any]:
    from app.agents.agent1_discovery.chunking import chunk_extracted_document
    from app.agents.agent1_discovery.procurement_facts import extract_procurement_facts

    scoped = tenant_id or _UNSCOPED_TENANT
    working = list(chunks)
    for extracted in extracted_documents or []:
        working.extend(
            chunk_extracted_document(
                extracted,
                tenant_id=scoped,
                document_id=extracted.file_id,
                source="upload",
            )
        )
    extraction = extract_procurement_facts(working)
    policy_hits = get_document_corpus().search(
        tenant_id=scoped,
        query=_POLICY_RETRIEVAL_QUERY,
        top_k=8,
    )
    status = extraction.status
    if parse_failures and status == "OK" and not any(
        fact.field == "amount" and fact.value for fact in extraction.facts
    ):
        status = "INSUFFICIENT_EVIDENCE"
    return {
        "status": status,
        "facts": [fact.model_dump(mode="json") for fact in extraction.facts],
        "conflicts": [item.model_dump(mode="json") for item in extraction.conflicts],
        "missing": extraction.missing,
        "policy_refs": [ref.model_dump(mode="json") for ref in extraction.policy_refs],
        "policy_hits": [hit.model_dump(mode="json") for hit in policy_hits],
        "parse_failures": parse_failures,
        "current_stage": None,
        "workflow_state": None,
        "completion_state": None,
        "exception_state": None,
        "extraction": extraction,
        "policy_hits_models": policy_hits,
    }


def _overlay_risk_facts(risk_facts: dict[str, Any], intelligence: dict[str, Any]) -> dict[str, Any]:
    from app.agents.agent1_discovery.procurement_facts import fact_map

    extraction = intelligence.get("extraction")
    if extraction is None:
        return risk_facts
    verified = fact_map(extraction)
    updated = dict(risk_facts)
    amount = verified.get("amount")
    if amount is not None:
        updated["purchase_amount"] = str(amount.value)
    currency = verified.get("currency")
    if currency is not None:
        updated["currency"] = str(currency.value)
    requester = verified.get("requester")
    if requester is not None:
        updated["requester"] = str(requester.value)
    vendor = verified.get("vendor")
    if vendor is not None and not updated.get("vendor_name"):
        updated["vendor_name"] = str(vendor.value)
    pr_id = verified.get("process_request_id")
    if pr_id is not None:
        updated["purchase_request_id"] = str(pr_id.value)
    budget = verified.get("budget")
    if budget is not None:
        updated["budget_amount"] = str(budget.value)
    quotes = verified.get("quotation_count")
    if quotes is not None:
        updated["quotation_count"] = int(quotes.value)
    return updated


def _evidence_from_intelligence(intelligence: dict[str, Any]) -> list[EvidenceReference]:
    refs: list[EvidenceReference] = []
    for fact in intelligence.get("facts") or []:
        for pointer in fact.get("evidence_refs") or []:
            refs.append(
                EvidenceReference(
                    field=str(fact.get("field") or "fact"),
                    file_id=UUID(str(pointer["document_id"])),
                    page=pointer.get("page"),
                    chunk_id=UUID(str(pointer["chunk_id"])) if pointer.get("chunk_id") else None,
                    document_version=pointer.get("document_version"),
                )
            )
    for hit in intelligence.get("policy_hits") or []:
        refs.append(
            EvidenceReference(
                field="policy",
                file_id=UUID(str(hit["document_id"])),
                page=hit.get("page"),
                chunk_id=UUID(str(hit["chunk_id"])) if hit.get("chunk_id") else None,
                document_version=hit.get("document_version"),
            )
        )
    return refs


def _message_status(process: ProcessJSON, *, had_partial_failure: bool) -> AgentMessageStatus:
    if process.missing_or_contradictory_fields:
        return "NEEDS_CLARIFICATION"
    if had_partial_failure:
        return "PARTIAL"
    return "COMPLETE"


def _wrap_message(
    process: ProcessJSON,
    *,
    evidence_references: list[EvidenceReference],
    had_partial_failure: bool,
    discovery_errors: list[str],
    process_id: UUID | None = None,
) -> DiscoveryAgentMessage:
    confidences = list(process.confidence.values()) if process.confidence else [0.0]
    overall = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
    payload = process.model_dump(mode="json")
    if discovery_errors:
        payload["discovery_errors"] = discovery_errors
    logger.info(
        "run_discovery_complete",
        extra={
            "status": _message_status(process, had_partial_failure=had_partial_failure),
            "activity_count": len(process.activities),
            "evidence_count": len(evidence_references),
            "error_count": len(discovery_errors),
            "overall_confidence": overall,
            "process_id": str(process_id) if process_id else None,
        },
    )
    kwargs: dict[str, Any] = {
        "sender": "agent1_discovery",
        "payload": payload,
        "evidence_references": evidence_references,
        "overall_confidence": overall,
        "status": _message_status(process, had_partial_failure=had_partial_failure),
    }
    if process_id is not None:
        kwargs["process_id"] = process_id
    return DiscoveryAgentMessage(**kwargs)


def _wrap_and_persist(
    db: Session | None,
    process: ProcessJSON,
    *,
    evidence_references: list[EvidenceReference],
    had_partial_failure: bool,
    discovery_errors: list[str],
    documents: list[dict[str, Any]],
    process_id: UUID | None = None,
    requester_user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    requester_email: str | None = None,
    requester_name: str | None = None,
    requester_department: str | None = None,
    entities: list[Any] | None = None,
    doc_types: list[str] | None = None,
) -> DiscoveryAgentMessage:
    message = _wrap_message(
        process,
        evidence_references=evidence_references,
        had_partial_failure=had_partial_failure,
        discovery_errors=discovery_errors,
        process_id=process_id,
    )
    try:
        persist_discovery(
            db,
            message,
            process,
            documents,
            tenant_id=tenant_id,
            requester_user_id=requester_user_id,
            requester_email=requester_email,
            requester_name=requester_name,
            requester_department=requester_department,
            entities=entities,
            doc_types=doc_types,
        )
    except Exception:
        logger.exception("persist_discovery_failed")
        payload = dict(message.payload)
        errors = list(payload.get("discovery_errors") or [])
        errors.append("Failed to persist discovery to the database")
        payload["discovery_errors"] = errors
        message.payload = payload
    return message


def run_discovery(
    files: list[Any],
    db: Session | None,
    *,
    process_id: UUID | None = None,
    requester_user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    requester_email: str | None = None,
    requester_name: str | None = None,
    requester_department: str | None = None,
) -> DiscoveryAgentMessage:
    """Ingest documents, discover a process, and return an informational discovery message.

    When ``process_id`` is provided, discovery is persisted onto that existing process
    row (Create Process → upload). When omitted, a new process id is allocated.

    Pipeline per file:
    validate_and_ingest → extract_text → classify_document → extract_entities
    → extract_relations → analyze_event_log (CSV only) → select_process_steps
    (documents) → build_process_json.
    """
    logger.info(
        "run_discovery_start",
        extra={
            "file_count": len(files) if files else 0,
            "process_id": str(process_id) if process_id else None,
        },
    )
    discovery_errors: list[str] = []

    if not files:
        discovery_errors.append("No files were provided to run_discovery")
        logger.warning("run_discovery_no_files")
        empty = ProcessJSON(
            missing_or_contradictory_fields=["documents"],
            confidence={"entities": 0.0, "relations": 0.0, "process_structure": 0.0},
        )
        return _wrap_and_persist(
            db,
            empty,
            evidence_references=[],
            had_partial_failure=True,
            discovery_errors=discovery_errors,
            documents=[],
            process_id=process_id,
            requester_user_id=requester_user_id,
            tenant_id=tenant_id,
            requester_email=requester_email,
            requester_name=requester_name,
            requester_department=requester_department,
        )

    all_entities: list[Entity] = []
    all_relations: list[Relation] = []
    evidence_references: list[EvidenceReference] = []
    documents: list[dict[str, Any]] = []
    extracted_documents: list[ExtractedDocument] = []
    doc_types: list[str] = []
    mining_result = ProcessMiningResult()
    had_partial_failure = False
    extracted_any = False
    stage_results: dict[str, StageExecutionMeta] = {}
    indexed_chunks: list[Any] = []
    parse_failures: list[str] = []

    with TemporaryDirectory(prefix="agent1_ingest_") as staging:
        staging_path = Path(staging)
        for index, raw in enumerate(files):
            buffered = _buffer_upload(raw)
            logger.info(
                "step_start",
                extra={
                    "step": "validate_and_ingest",
                    "index": index,
                    "upload_filename": buffered.filename,
                    "size": len(buffered.content),
                },
            )
            try:
                ingested = validate_and_ingest(buffered, db)
            except Exception:
                logger.exception(
                    "step_failed",
                    extra={"step": "validate_and_ingest", "upload_filename": buffered.filename},
                )
                discovery_errors.append(f"validate_and_ingest failed for {buffered.filename}")
                had_partial_failure = True
                continue

            logger.info(
                "step_end",
                extra={
                    "step": "validate_and_ingest",
                    "upload_filename": buffered.filename,
                    "status": ingested.status,
                    "rejection_reason": ingested.rejection_reason,
                    "file_id": str(ingested.file_id),
                    "size_bytes": ingested.size_bytes,
                },
            )
            documents.append(
                {
                    "file_id": ingested.file_id,
                    "original_filename": buffered.filename,
                    "sanitized_filename": sanitize_filename(buffered.filename),
                    "mime_type": ingested.mime_type,
                    "size_bytes": ingested.size_bytes,
                    "ingest_status": ingested.status,
                    "doc_type": None,
                }
            )
            if ingested.status != "accepted":
                had_partial_failure = True
                discovery_errors.append(
                    f"ingest rejected {buffered.filename}: {ingested.rejection_reason}"
                )
                continue

            suffix = Path(sanitize_filename(buffered.filename)).suffix or ""
            saved = staging_path / f"{ingested.file_id}{suffix}"
            saved.write_bytes(buffered.content)

            logger.info(
                "step_start",
                extra={"step": "extract_text", "file_id": str(ingested.file_id), "suffix": suffix},
            )
            try:
                extracted = extract_text(ingested.file_id, saved)
            except Exception:
                logger.exception(
                    "step_failed",
                    extra={"step": "extract_text", "file_id": str(ingested.file_id)},
                )
                discovery_errors.append(f"extract_text crashed for {buffered.filename}")
                had_partial_failure = True
                continue

            logger.info(
                "step_end",
                extra={
                    "step": "extract_text",
                    "file_id": str(ingested.file_id),
                    "status": extracted.status,
                    "failure_reason": extracted.failure_reason,
                    "page_count": len(extracted.pages),
                    "text_chars": sum(len(page.text or "") for page in extracted.pages),
                    "extraction_method": extracted.extraction_method,
                },
            )
            if extracted.status != "extracted":
                had_partial_failure = True
                discovery_errors.append(
                    f"extract_text failed for {buffered.filename}: {extracted.failure_reason}"
                )
                parse_failures.append(
                    extracted.failure_reason or "INSUFFICIENT_EVIDENCE"
                )
                continue

            extracted_any = True
            extracted_documents.append(extracted)

            logger.info(
                "step_start",
                extra={"step": "classify_document", "file_id": str(ingested.file_id)},
            )
            classification = classify_document(extracted)
            doc_types.append(classification.doc_type)
            if documents:
                documents[-1]["doc_type"] = classification.doc_type
            try:
                indexed_chunks.extend(
                    _index_extracted_document(
                        tenant_id=tenant_id,
                        filename=buffered.filename,
                        content=buffered.content,
                        extracted=extracted,
                        document_type=classification.doc_type,
                        mime_type=ingested.mime_type,
                    )
                )
                if documents:
                    documents[-1]["content_hash"] = content_sha256(buffered.content)
                    documents[-1]["tenant_id"] = str(tenant_id) if tenant_id else None
                    documents[-1]["version"] = "1"
                    documents[-1]["source"] = "upload"
            except Exception:
                logger.exception("document_index_failed", extra={"file_id": str(ingested.file_id)})
                discovery_errors.append(f"document index failed for {buffered.filename}")
            stage_results[f"classify_document:{ingested.file_id}"] = StageExecutionMeta(
                degraded=False,
                confidence=classification.confidence,
                method="rules",
            )
            logger.info(
                "step_end",
                extra={
                    "step": "classify_document",
                    "doc_type": classification.doc_type,
                    "confidence": classification.confidence,
                    "reasons": classification.reasons,
                },
            )

            logger.info(
                "step_start",
                extra={"step": "extract_entities", "doc_type": classification.doc_type},
            )
            try:
                entities = extract_entities(extracted, classification.doc_type)
            except Exception:
                logger.exception(
                    "step_failed",
                    extra={"step": "extract_entities", "file_id": str(ingested.file_id)},
                )
                discovery_errors.append(f"extract_entities crashed for {buffered.filename}")
                had_partial_failure = True
                entities = []
            entity_confidence = (
                _mean([entity.confidence for entity in entities]) if entities else 0.0
            )
            stage_results[f"extract_entities:{ingested.file_id}"] = StageExecutionMeta(
                degraded=False,
                confidence=entity_confidence,
                method="rules",
            )
            logger.info(
                "step_end",
                extra={
                    "step": "extract_entities",
                    "entity_count": len(entities),
                    "entity_types": [entity.entity_type for entity in entities],
                },
            )

            logger.info(
                "step_start",
                extra={"step": "extract_relations", "entity_count": len(entities)},
            )
            try:
                relations, relation_meta = extract_relations(
                    extracted, entities, classification.doc_type
                )
                stage_results[f"extract_relations:{ingested.file_id}"] = relation_meta
            except Exception:
                logger.exception(
                    "step_failed",
                    extra={"step": "extract_relations", "file_id": str(ingested.file_id)},
                )
                discovery_errors.append(f"extract_relations crashed for {buffered.filename}")
                had_partial_failure = True
                relations = []
                stage_results[f"extract_relations:{ingested.file_id}"] = StageExecutionMeta(
                    degraded=True,
                    confidence=0.0,
                    method="failed",
                )
            logger.info(
                "step_end",
                extra={"step": "extract_relations", "relation_count": len(relations)},
            )

            all_entities.extend(entities)
            all_relations.extend(relations)
            evidence_references.extend(_evidence_for_entities(ingested.file_id, entities))
            evidence_references.append(
                EvidenceReference(field="document", file_id=ingested.file_id, page=1)
            )

            if suffix.lower() == ".csv":
                logger.info("step_start", extra={"step": "analyze_event_log", "path": str(saved)})
                try:
                    mining_result = analyze_event_log(saved)
                except Exception:
                    logger.exception("step_failed", extra={"step": "analyze_event_log"})
                    discovery_errors.append(f"analyze_event_log crashed for {buffered.filename}")
                    had_partial_failure = True
                else:
                    stage_results["analyze_event_log"] = StageExecutionMeta(
                        degraded=False,
                        confidence=0.95 if mining_result.most_frequent_variant else 0.5,
                        method="pm4py",
                    )
                    logger.info(
                        "step_end",
                        extra={
                            "step": "analyze_event_log",
                            "variant": mining_result.most_frequent_variant,
                            "rework_count": len(mining_result.rework_activities),
                            "exception_count": len(mining_result.flagged_exceptions),
                        },
                    )

    logger.info(
        "step_start",
        extra={
            "step": "select_process_steps",
            "entity_count": len(all_entities),
            "relation_count": len(all_relations),
            "has_event_log_variant": bool(mining_result.most_frequent_variant),
            "extracted_docs": len(extracted_documents),
        },
    )
    step_selection: StepSelectionResult | None = None
    if not mining_result.most_frequent_variant:
        try:
            step_selection, selection_meta = select_process_steps(
                extracted_documents,
                all_entities,
                all_relations,
                doc_types=doc_types,
            )
            stage_results["select_process_steps"] = selection_meta
        except Exception:
            logger.exception("step_failed", extra={"step": "select_process_steps"})
            discovery_errors.append("select_process_steps crashed")
            had_partial_failure = True
            step_selection = None
            stage_results["select_process_steps"] = StageExecutionMeta(
                degraded=True,
                confidence=0.0,
                method="failed",
            )
    else:
        stage_results["select_process_steps"] = StageExecutionMeta(
            degraded=False,
            confidence=0.95,
            method="event_log_variant",
        )
    logger.info(
        "step_end",
        extra={
            "step": "select_process_steps",
            "selected_count": len(step_selection.steps) if step_selection else 0,
            "summary": step_selection.selection_summary if step_selection else None,
            "skipped_for_event_log": bool(mining_result.most_frequent_variant),
        },
    )

    logger.info(
        "step_start",
        extra={
            "step": "build_process_json",
            "entity_count": len(all_entities),
            "relation_count": len(all_relations),
            "extracted_any": extracted_any,
        },
    )
    if not extracted_any:
        discovery_errors.append(
            "No document produced extracted text; ProcessJSON was built from empty evidence"
        )
        had_partial_failure = True
    process = build_process_json(
        all_entities,
        all_relations,
        mining_result,
        step_selection=step_selection,
    )
    joined_text = "\n".join(
        page.text or ""
        for doc in extracted_documents
        for page in (doc.pages or [])
    )
    pipeline_degraded = any(meta.degraded for meta in stage_results.values())
    try:
        risk_facts_model = RiskFacts.from_discovery(
            all_entities,
            doc_types=doc_types,
            joined_text=joined_text,
            degraded=pipeline_degraded,
        )
        risk_facts = validate_risk_facts(risk_facts_model.model_dump(mode="json")).model_dump(
            mode="json"
        )
        intelligence = _document_intelligence(
            tenant_id=tenant_id,
            chunks=indexed_chunks,
            parse_failures=parse_failures,
            extracted_documents=extracted_documents,
        )
        risk_facts = _overlay_risk_facts(risk_facts, intelligence)
        evidence_references.extend(_evidence_from_intelligence(intelligence))
        serializable = {
            key: value
            for key, value in intelligence.items()
            if key not in {"extraction", "policy_hits_models"}
        }
        process.analytics = {
            **(process.analytics or {}),
            "risk_facts": risk_facts,
            "document_intelligence": serializable,
            "discovery_stages": {
                name: meta.model_dump(mode="json") for name, meta in stage_results.items()
            },
            "degraded": pipeline_degraded,
        }
        if intelligence.get("status") == "DISCOVERY_CONFLICT":
            process.missing_or_contradictory_fields = list(
                dict.fromkeys(
                    [
                        *(process.missing_or_contradictory_fields or []),
                        *(f"conflict:{item.field}" for item in intelligence["extraction"].conflicts),
                    ]
                )
            )
        elif intelligence.get("status") == "INSUFFICIENT_EVIDENCE":
            process.missing_or_contradictory_fields = list(
                dict.fromkeys(
                    [
                        *(process.missing_or_contradictory_fields or []),
                        *intelligence.get("missing", []),
                    ]
                )
            )
    except Exception:
        logger.exception("step_failed", extra={"step": "extract_risk_facts"})
        discovery_errors.append("extract_risk_facts crashed")
        had_partial_failure = True
        risk_facts = RiskFacts(degraded=True, confidence=0.0).model_dump(mode="json")
        process.analytics = {
            **(process.analytics or {}),
            "risk_facts": risk_facts,
            "discovery_stages": {
                name: meta.model_dump(mode="json") for name, meta in stage_results.items()
            },
            "degraded": True,
        }
    logger.info(
        "step_end",
        extra={
            "step": "build_process_json",
            "process_name": process.process_name,
            "activity_count": len(process.activities),
            "rule_count": len(process.rules),
            "dependency_count": len(process.dependencies),
            "missing_count": len(process.missing_or_contradictory_fields),
            "risk_purchase_amount": risk_facts.get("purchase_amount"),
        },
    )
    return _wrap_and_persist(
        db,
        process,
        evidence_references=evidence_references,
        had_partial_failure=had_partial_failure,
        discovery_errors=discovery_errors,
        documents=documents,
        process_id=process_id,
        requester_user_id=requester_user_id,
        tenant_id=tenant_id,
        requester_email=requester_email,
        requester_name=requester_name,
        requester_department=requester_department,
        entities=all_entities,
        doc_types=doc_types,
    )
