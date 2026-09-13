"""Write Agent 1 discovery results to Postgres or Supabase REST."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.agents.agent1_discovery.schemas import ProcessJSON
from app.core.logging import get_logger
from app.models.agent_message import AgentMessageRecord
from app.models.document import DiscoveredDocument
from app.models.process import Process, ProcessExceptionRow, ProcessTask
from app.schemas.agent_message import DiscoveryAgentMessage

logger = get_logger(__name__)


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _process_view(row: dict[str, Any], process_json: dict[str, Any] | None = None) -> SimpleNamespace:
    meta: dict[str, Any] = {}
    description = row.get("description")
    if isinstance(description, str) and description.startswith("{"):
        try:
            import json

            parsed = json.loads(description)
            if isinstance(parsed, dict):
                meta = parsed
        except Exception:
            meta = {}
    payload = process_json if process_json is not None else (row.get("process_json") or {})
    if not payload:
        payload = meta.get("process_json") or {}
    return SimpleNamespace(
        id=_as_uuid(row["id"]),
        name=row.get("name") or "Discovered process",
        status=row.get("status") or "draft",
        discovery_status=row.get("discovery_status") or meta.get("discovery_status"),
        overall_confidence=row.get("overall_confidence") if row.get("overall_confidence") is not None else meta.get("overall_confidence"),
        process_json=payload if isinstance(payload, dict) else {},
        created_at=_parse_dt(row.get("created_at")),
    )


def _task_view(row: dict[str, Any], index: int) -> SimpleNamespace:
    return SimpleNamespace(
        sort_order=row.get("sort_order") if row.get("sort_order") is not None else index,
        title=row.get("title") or f"Step {index + 1}",
        actor=row.get("actor"),
        system=row.get("system"),
        avg_duration=row.get("avg_duration"),
        status=row.get("status") or "pending",
        description=row.get("description"),
    )


def persist_discovery(
    db: Session | None,
    message: DiscoveryAgentMessage,
    process: ProcessJSON,
    documents: list[dict[str, Any]],
    *,
    tenant_id: UUID | None = None,
    requester_user_id: UUID | None = None,
    requester_email: str | None = None,
    requester_name: str | None = None,
    requester_department: str | None = None,
    entities: list[Any] | None = None,
    doc_types: list[str] | None = None,
) -> Any:
    """Store the discovered workflow on the process identified by message.process_id.

    If a process row already exists (Create Process → upload), discovery fields are
    updated in place. current_stage is never written here — Agent 4 owns stages.
    """
    extras = dict(
        tenant_id=tenant_id,
        requester_user_id=requester_user_id,
        requester_email=requester_email,
        requester_name=requester_name,
        requester_department=requester_department,
        entities=entities,
        doc_types=doc_types,
    )
    if db is not None:
        return _persist_sqlalchemy(db, message, process, documents, **extras)
    return _persist_rest(message, process, documents, **extras)


def _store_process_context(
    row: Process,
    message: DiscoveryAgentMessage,
    process: ProcessJSON,
    documents: list[dict[str, Any]],
    *,
    tenant_id: UUID | None = None,
    requester_user_id: UUID | None = None,
    requester_email: str | None = None,
    requester_name: str | None = None,
    requester_department: str | None = None,
    entities: list[Any] | None = None,
    doc_types: list[str] | None = None,
) -> dict[str, Any]:
    from app.process_context.from_discovery import context_from_discovery
    from app.process_context.service import context_from_process_row, merge_process_context

    existing = context_from_process_row(row)
    patch = context_from_discovery(
        process,
        message,
        tenant_id=tenant_id or getattr(row, "tenant_id", None),
        requester_user_id=requester_user_id or getattr(row, "created_by", None),
        requester_email=requester_email or getattr(row, "requester_email", None),
        requester_name=requester_name,
        requester_department=requester_department or getattr(row, "department", None),
        documents=documents,
        entities=entities,
        doc_types=doc_types,
    )
    merged = merge_process_context(existing, patch, incoming_source="extracted_evidence")
    payload = merged.model_dump(mode="json")
    row.process_context = payload
    if merged.tenant_id:
        row.tenant_id = merged.tenant_id
    if merged.approver.user_id:
        row.designated_approver_id = merged.approver.user_id
    return payload


def _apply_discovery_fields(row: Process, message: DiscoveryAgentMessage, process: ProcessJSON) -> None:
    name = process.process_name or row.name or "Discovered process"
    row.name = name
    if not row.description:
        row.description = "Workflow discovered by Agent 1 from uploaded documents"
    if not row.process_type or row.process_type in {"", "general", "standard"}:
        row.process_type = "discovered"
    if message.status == "COMPLETE" and row.status == "draft":
        row.status = "active"
    row.process_json = message.payload
    row.overall_confidence = message.overall_confidence
    row.discovery_status = message.status
    row.trace_id = message.trace_id
    row.message_id = message.message_id


def _replace_discovery_tasks(db: Session, process_id: UUID, process: ProcessJSON) -> None:
    """Replace discovery-derived task rows for early-stage processes only."""
    existing = db.query(ProcessTask).filter(ProcessTask.process_id == process_id).all()
    for task in existing:
        db.delete(task)
    db.flush()
    for index, activity in enumerate(process.activities):
        details: list[str] = []
        if activity.entry_conditions:
            details.append("Entry: " + "; ".join(activity.entry_conditions))
        if activity.exit_conditions:
            details.append("Exit: " + "; ".join(activity.exit_conditions))
        db.add(
            ProcessTask(
                id=uuid4(),
                process_id=process_id,
                title=activity.name,
                description="\n".join(details) or None,
                status="pending",
                sort_order=index,
                actor=activity.actor,
                system=activity.system,
                avg_duration=activity.avg_duration,
            )
        )


def _persist_sqlalchemy(
    db: Session,
    message: DiscoveryAgentMessage,
    process: ProcessJSON,
    documents: list[dict[str, Any]],
    *,
    tenant_id: UUID | None = None,
    requester_user_id: UUID | None = None,
    requester_email: str | None = None,
    requester_name: str | None = None,
    requester_department: str | None = None,
    entities: list[Any] | None = None,
    doc_types: list[str] | None = None,
) -> Process:
    existing = db.get(Process, message.process_id)
    updated_existing = existing is not None
    if existing is not None:
        row = existing
        _apply_discovery_fields(row, message, process)
        _store_process_context(
            row,
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
        stage = (row.current_stage or "DRAFT").upper()
        if stage in {"DRAFT", "DISCOVERING"}:
            _replace_discovery_tasks(db, row.id, process)
    else:
        name = process.process_name or "Discovered process"
        row = Process(
            id=message.process_id,
            name=name,
            description="Workflow discovered by Agent 1 from uploaded documents",
            process_type="discovered",
            status="draft" if message.status != "COMPLETE" else "active",
            process_json=message.payload,
            overall_confidence=message.overall_confidence,
            discovery_status=message.status,
            trace_id=message.trace_id,
            message_id=message.message_id,
            current_stage="DRAFT",
            tenant_id=tenant_id,
            process_context={},
        )
        db.add(row)
        db.flush()
        _store_process_context(
            row,
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
        _replace_discovery_tasks(db, row.id, process)

    for item in process.exceptions:
        db.add(
            ProcessExceptionRow(
                id=uuid4(),
                process_id=row.id,
                severity="medium",
                exception_type=item.kind or "discovered",
                description=item.description,
                status="open",
            )
        )

    for doc in documents:
        file_id = doc.get("file_id")
        doc_uuid = file_id if isinstance(file_id, UUID) else uuid4()
        existing_doc = db.get(DiscoveredDocument, doc_uuid)
        if existing_doc is None:
            existing_doc = DiscoveredDocument(id=doc_uuid)
            db.add(existing_doc)
        existing_doc.process_id = row.id
        existing_doc.original_filename = doc.get("original_filename")
        existing_doc.sanitized_filename = doc.get("sanitized_filename")
        existing_doc.mime_type = doc.get("mime_type")
        existing_doc.size_bytes = doc.get("size_bytes")
        existing_doc.ingest_status = doc.get("ingest_status")
        existing_doc.doc_type = doc.get("doc_type")
        existing_doc.tenant_id = tenant_id
        existing_doc.content_hash = doc.get("content_hash")
        existing_doc.source = doc.get("source") or "upload"
        existing_doc.version = str(doc.get("version") or "1")
        existing_doc.is_active = True
        existing_doc.evidence_ref = str(doc_uuid)

    if tenant_id is not None:
        from app.ir.corpus import get_document_corpus
        from app.models.document import DocumentChunk

        indexed_ids = {
            (doc.get("file_id") if isinstance(doc.get("file_id"), UUID) else None)
            for doc in documents
        }
        for chunk in get_document_corpus().active_chunks(tenant_id):
            if chunk.document_id not in indexed_ids:
                continue
            if db.get(DocumentChunk, chunk.chunk_id) is not None:
                continue
            db.add(
                DocumentChunk(
                    id=chunk.chunk_id,
                    tenant_id=chunk.tenant_id,
                    document_id=chunk.document_id,
                    process_id=row.id,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page,
                    section_title=chunk.section,
                    text_content=chunk.text,
                    embedding=list(chunk.embedding),
                    metadata_json=chunk.metadata,
                    document_version=chunk.document_version,
                    is_active=True,
                )
            )

    db.add(
        AgentMessageRecord(
            id=message.message_id,
            from_agent=message.sender,
            to_agent="human",
            message_type="discovery",
            content=message.model_dump(mode="json"),
            process_id=row.id,
            status="sent",
        )
    )
    db.commit()
    db.refresh(row)
    logger.info(
        "discovery_persisted",
        extra={
            "process_id": str(row.id),
            "task_count": len(process.activities),
            "document_count": len(documents),
            "store": "postgres",
            "updated_existing": updated_existing,
        },
    )
    return row


def _jsonable_docs(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for doc in documents:
        item = dict(doc)
        if isinstance(item.get("file_id"), UUID):
            item["file_id"] = str(item["file_id"])
        out.append(item)
    return out


def _persist_rest(
    message: DiscoveryAgentMessage,
    process: ProcessJSON,
    documents: list[dict[str, Any]],
    *,
    tenant_id: UUID | None = None,
    requester_user_id: UUID | None = None,
    requester_email: str | None = None,
    requester_name: str | None = None,
    requester_department: str | None = None,
    entities: list[Any] | None = None,
    doc_types: list[str] | None = None,
) -> SimpleNamespace:
    import json

    from app.core.supabase_rest import rest_insert, rest_select, rest_update
    from app.process_context.from_discovery import context_from_discovery
    from app.process_context.schemas import ProcessContext
    from app.process_context.service import empty_process_context, merge_process_context

    name = process.process_name or "Discovered process"
    process_id = str(message.process_id)
    existing_rows = rest_select("processes", {"id": f"eq.{process_id}", "select": "*"})
    existing_ctx: dict[str, Any] = {}
    existing_tenant = tenant_id
    if existing_rows:
        existing_ctx = existing_rows[0].get("process_context") or {}
        existing_tenant = existing_tenant or existing_rows[0].get("tenant_id")
    tenant_uuid = UUID(str(existing_tenant)) if existing_tenant else None
    current = (
        ProcessContext.model_validate(existing_ctx)
        if isinstance(existing_ctx, dict) and existing_ctx.get("process_id")
        else empty_process_context(message.process_id, tenant_id=tenant_uuid)
    )
    patch_ctx = context_from_discovery(
        process,
        message,
        tenant_id=tenant_uuid,
        requester_user_id=requester_user_id,
        requester_email=requester_email,
        requester_name=requester_name,
        requester_department=requester_department,
        documents=documents,
        entities=entities,
        doc_types=doc_types,
    )
    context_payload = merge_process_context(
        current, patch_ctx, incoming_source="extracted_evidence"
    ).model_dump(mode="json")
    meta = {
        "overall_confidence": message.overall_confidence,
        "discovery_status": message.status,
        "trace_id": str(message.trace_id),
        "message_id": str(message.message_id),
        "documents": _jsonable_docs(documents),
        "process_json": message.payload,
    }
    if existing_rows:
        patch = {
            "name": name,
            "process_json": message.payload,
            "overall_confidence": message.overall_confidence,
            "discovery_status": message.status,
            "trace_id": str(message.trace_id),
            "message_id": str(message.message_id),
            "description": json.dumps(meta),
            "process_context": context_payload,
        }
        if tenant_uuid:
            patch["tenant_id"] = str(tenant_uuid)
        try:
            stored = rest_update("processes", {"id": f"eq.{process_id}"}, patch)
        except Exception:
            stored = rest_update(
                "processes",
                {"id": f"eq.{process_id}"},
                {
                    "name": name,
                    "description": json.dumps(meta),
                    "status": "draft" if message.status != "COMPLETE" else "active",
                },
            )
        if not stored:
            stored = existing_rows[0]
    else:
        base_row = {
            "id": process_id,
            "name": name,
            "description": json.dumps(meta),
            "process_type": "discovered",
            "status": "draft" if message.status != "COMPLETE" else "active",
        }
        full_row = {
            **base_row,
            "process_json": message.payload,
            "overall_confidence": message.overall_confidence,
            "discovery_status": message.status,
            "trace_id": str(message.trace_id),
            "message_id": str(message.message_id),
            "process_context": context_payload,
        }
        if tenant_uuid:
            full_row["tenant_id"] = str(tenant_uuid)
        try:
            stored = rest_insert("processes", full_row)
        except Exception:
            stored = rest_insert("processes", base_row)

    for index, activity in enumerate(process.activities):
        details: list[str] = []
        if activity.actor:
            details.append(f"Actor: {activity.actor}")
        if activity.entry_conditions:
            details.append("Entry: " + "; ".join(activity.entry_conditions))
        rest_insert(
            "tasks",
            {
                "process_id": process_id,
                "title": activity.name,
                "description": " | ".join(details) or None,
                "status": "pending",
                "priority": "medium",
            },
        )
        _ = index

    for item in process.exceptions:
        rest_insert(
            "exceptions",
            {
                "process_id": process_id,
                "severity": "medium",
                "type": item.kind or "discovered",
                "description": item.description,
                "status": "open",
            },
        )

    rest_insert(
        "agent_messages",
        {
            "id": str(message.message_id),
            "from_agent": message.sender,
            "to_agent": "human",
            "message_type": "discovery",
            "content": message.model_dump(mode="json"),
            "process_id": process_id,
            "status": "sent",
        },
    )
    logger.info(
        "discovery_persisted",
        extra={
            "process_id": process_id,
            "task_count": len(process.activities),
            "document_count": len(documents),
            "store": "supabase_rest",
            "updated_existing": bool(existing_rows),
        },
    )
    return _process_view(stored, message.payload)


def get_process(db: Session | None, process_id: UUID) -> Any | None:
    if db is not None:
        return db.get(Process, process_id)
    from app.core.supabase_rest import rest_select

    rows = rest_select("processes", {"id": f"eq.{process_id}", "select": "*"})
    if not rows:
        return None
    messages = rest_select(
        "agent_messages",
        {
            "process_id": f"eq.{process_id}",
            "select": "content,created_at",
            "order": "created_at.desc",
            "limit": "1",
        },
    )
    payload = None
    if messages:
        content = messages[0].get("content") or {}
        if isinstance(content, dict):
            payload = content.get("payload")
    return _process_view(rows[0], payload)


def list_recent_processes(db: Session | None, *, limit: int = 20) -> list[Any]:
    if db is not None:
        return list(db.query(Process).order_by(Process.created_at.desc()).limit(limit).all())
    from app.core.supabase_rest import rest_select

    rows = rest_select(
        "processes",
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": str(limit),
        },
    )
    return [_process_view(row) for row in rows]


def list_process_tasks(db: Session | None, process_id: UUID) -> list[Any]:
    if db is not None:
        return list(
            db.query(ProcessTask)
            .filter(ProcessTask.process_id == process_id)
            .order_by(ProcessTask.sort_order.asc())
            .all()
        )
    from app.core.supabase_rest import rest_select

    rows = rest_select(
        "tasks",
        {
            "process_id": f"eq.{process_id}",
            "select": "*",
            "order": "created_at.asc",
        },
    )
    return [_task_view(row, index) for index, row in enumerate(rows)]
