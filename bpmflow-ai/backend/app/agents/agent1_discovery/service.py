"""Assemble Agent 1 outputs into a ProcessJSON document.

Never invent values: if evidence is missing or contradictory, record the field
in `missing_or_contradictory_fields` and leave it empty.
"""

from __future__ import annotations

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
from app.agents.agent1_discovery.persistence import persist_discovery
from app.agents.agent1_discovery.process_mining import analyze_event_log
from app.agents.agent1_discovery.schemas import (
    Entity,
    ProcessActivity,
    ProcessDependency,
    ProcessException,
    ProcessJSON,
    ProcessMiningResult,
    ProcessRule,
    Relation,
)
from app.core.logging import get_logger
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


def build_process_json(
    entities: list[Entity],
    relations: list[Relation],
    mining_result: ProcessMiningResult,
) -> ProcessJSON:
    missing: list[str] = []

    name_values = [
        entity.value
        for entity in entities
        if entity.entity_type in {"process", "process_name", "process_title"}
    ]
    process_name, name_conflict = _unique_or_conflict(name_values)
    if name_conflict:
        missing.append("process_name (contradictory evidence)")
    elif process_name is None:
        missing.append("process_name")

    activity_names = list(mining_result.most_frequent_variant)
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
    if not activity_names:
        missing.append("activities")

    actors_by_task: dict[str, list[str]] = defaultdict(list)
    rules_by_task: dict[str, list[Relation]] = defaultdict(list)
    for relation in relations:
        if relation.predicate == "actor-performs-task":
            actors_by_task[_norm(relation.object)].append(relation.subject)
        elif relation.predicate == "rule-controls-task":
            rules_by_task[_norm(relation.object)].append(relation)

    systems = [entity.value for entity in entities if entity.entity_type == "system"]
    _, system_conflict = _unique_or_conflict(systems)
    if system_conflict:
        missing.append("system (contradictory evidence)")

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
        if duration is None:
            missing.append(f"activities.{name}.avg_duration")
        else:
            filled_slots += 1

        controlling = rules_by_task.get(key, [])
        entry = [rel.subject for rel in controlling]
        if entry:
            filled_slots += 1
        else:
            missing.append(f"activities.{name}.entry_conditions")

        # Exit conditions are not implied by precedes/performs relations.
        missing.append(f"activities.{name}.exit_conditions")

        activities.append(
            ProcessActivity(
                name=name,
                actor=actor,
                system=activity_system,
                avg_duration=duration,
                entry_conditions=entry,
                exit_conditions=[],
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
        1.0 if mining_result.most_frequent_variant else 0.0,
        1.0 if dependencies else 0.0,
        fill_rate,
    ]
    confidence = {
        "entities": _mean([entity.confidence for entity in entities]),
        "relations": _mean([relation.confidence for relation in relations]),
        "process_structure": _mean(structure_parts),
    }

    # Preserve order while dropping duplicate gap labels.
    deduped_missing: list[str] = []
    seen_missing: set[str] = set()
    for item in missing:
        if item not in seen_missing:
            seen_missing.add(item)
            deduped_missing.append(item)

    return ProcessJSON(
        process_name=process_name,
        activities=activities,
        rules=rules,
        dependencies=dependencies,
        exceptions=exceptions,
        missing_or_contradictory_fields=deduped_missing,
        confidence=confidence,
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
        },
    )
    return DiscoveryAgentMessage(
        sender="agent1_discovery",
        payload=payload,
        evidence_references=evidence_references,
        overall_confidence=overall,
        status=_message_status(process, had_partial_failure=had_partial_failure),
    )


def _wrap_and_persist(
    db: Session | None,
    process: ProcessJSON,
    *,
    evidence_references: list[EvidenceReference],
    had_partial_failure: bool,
    discovery_errors: list[str],
    documents: list[dict[str, Any]],
) -> DiscoveryAgentMessage:
    message = _wrap_message(
        process,
        evidence_references=evidence_references,
        had_partial_failure=had_partial_failure,
        discovery_errors=discovery_errors,
    )
    try:
        persist_discovery(db, message, process, documents)
    except Exception:
        logger.exception("persist_discovery_failed")
        payload = dict(message.payload)
        errors = list(payload.get("discovery_errors") or [])
        errors.append("Failed to persist discovery to the database")
        payload["discovery_errors"] = errors
        message.payload = payload
    return message


def run_discovery(files: list[Any], db: Session | None) -> DiscoveryAgentMessage:
    """Ingest documents, discover a process, and return an informational discovery message.

    Pipeline per file:
    validate_and_ingest → extract_text → classify_document → extract_entities
    → extract_relations → analyze_event_log (CSV only). Then build_process_json.
    """
    logger.info("run_discovery_start", extra={"file_count": len(files) if files else 0})
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
        )

    all_entities: list[Entity] = []
    all_relations: list[Relation] = []
    evidence_references: list[EvidenceReference] = []
    documents: list[dict[str, Any]] = []
    mining_result = ProcessMiningResult()
    had_partial_failure = False
    extracted_any = False

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
                continue

            extracted_any = True

            logger.info(
                "step_start",
                extra={"step": "classify_document", "file_id": str(ingested.file_id)},
            )
            classification = classify_document(extracted)
            if documents:
                documents[-1]["doc_type"] = classification.doc_type
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
            entities = extract_entities(extracted, classification.doc_type)
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
                relations = extract_relations(extracted, entities, classification.doc_type)
            except Exception:
                logger.exception(
                    "step_failed",
                    extra={"step": "extract_relations", "file_id": str(ingested.file_id)},
                )
                discovery_errors.append(f"extract_relations crashed for {buffered.filename}")
                had_partial_failure = True
                relations = []
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
    process = build_process_json(all_entities, all_relations, mining_result)
    logger.info(
        "step_end",
        extra={
            "step": "build_process_json",
            "process_name": process.process_name,
            "activity_count": len(process.activities),
            "rule_count": len(process.rules),
            "dependency_count": len(process.dependencies),
            "missing_count": len(process.missing_or_contradictory_fields),
        },
    )
    return _wrap_and_persist(
        db,
        process,
        evidence_references=evidence_references,
        had_partial_failure=had_partial_failure,
        discovery_errors=discovery_errors,
        documents=documents,
    )
