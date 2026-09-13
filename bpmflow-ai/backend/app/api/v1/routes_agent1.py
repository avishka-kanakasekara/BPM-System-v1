"""Agent 1 HTTP routes."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.agent1_discovery.persistence import (
    get_process,
    list_process_tasks,
    list_recent_processes,
)
from app.agents.agent1_discovery.ingest import ingest_bytes
from app.agents.agent1_discovery.service import run_discovery
from app.core.config import settings
from app.core.database import get_sync_db
from app.core.security import get_current_user
from app.ir.corpus import get_document_corpus
from app.schemas.agent_message import DiscoveryAgentMessage
from app.schemas.auth import CurrentUser

router = APIRouter()

_ALLOWED = ", ".join(ext.upper() for ext in settings.allowed_file_types_list)
_FILES_DESCRIPTION = (
    f"Upload one or more files. Allowed types from ALLOWED_FILE_TYPES: {_ALLOWED}. "
    f"Maximum size {settings.MAX_UPLOAD_MB} MB each."
)

UploadFiles = Annotated[
    list[UploadFile],
    File(
        description=_FILES_DESCRIPTION,
        json_schema_extra={
            "type": "array",
            "items": {"type": "string", "format": "binary"},
        },
    ),
]


class WorkflowStep(BaseModel):
    order: int
    title: str
    actor: str | None = None
    system: str | None = None
    avg_duration: float | None = None
    status: str = "pending"
    description: str | None = None


class ProcessSummary(BaseModel):
    process_id: UUID
    name: str
    status: str
    discovery_status: str | None = None
    overall_confidence: float | None = None
    activity_count: int = 0
    created_at: str | None = None


class ProcessDetail(BaseModel):
    process_id: UUID
    name: str
    status: str
    discovery_status: str | None = None
    overall_confidence: float | None = None
    workflow: list[WorkflowStep]
    process_json: dict[str, Any]
    created_at: str | None = None


class DocumentIngestResponse(BaseModel):
    document_id: UUID
    tenant_id: UUID
    filename: str
    document_type: str | None = None
    source: str | None = None
    version: str
    is_active: bool
    content_hash: str
    parse_status: str
    parse_failure: str | None = None
    chunk_count: int
    reused: bool = False


class SearchRequest(BaseModel):
    query: str
    top_k: int = 8
    document_id: UUID | None = None


class SearchHit(BaseModel):
    document_id: UUID
    chunk_id: UUID
    page: int | None = None
    score: float
    text: str
    snippet: str
    document_version: str | None = None
    filename: str | None = None
    document_type: str | None = None
    source: str | None = None
    section: str | None = None


@router.post(
    "/discover",
    response_model=DiscoveryAgentMessage,
    summary="Discover a process from documents",
    description=(
        "Accepts multipart file uploads (PDF, DOCX, CSV — allow-list from "
        "`ALLOWED_FILE_TYPES`). Optional form field `process_id` attaches discovery "
        "to an existing Create Process row. Returns an informational discovery "
        "message only; Agent 1 does not approve or decide. Does not modify "
        "current_stage — Agent 4 owns workflow stages."
    ),
)
def discover(
    files: UploadFiles,
    process_id: Annotated[UUID | None, Form()] = None,
    db: Session | None = Depends(get_sync_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DiscoveryAgentMessage:
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")
    allowed = settings.allowed_file_types_list
    for upload in files:
        name = upload.filename or ""
        suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if suffix not in allowed:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type for '{name}'. "
                    f"Allowed: {', '.join(ext.upper() for ext in allowed)}"
                ),
            )
        size = getattr(upload, "size", None)
        if isinstance(size, int) and size > settings.max_upload_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File '{name}' exceeds the {settings.MAX_UPLOAD_MB} MB limit.",
            )
    if process_id is not None:
        existing = get_process(db, process_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Process not found")
    return run_discovery(
        files,
        db,
        process_id=process_id,
        requester_user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        requester_email=current_user.email,
        requester_name=current_user.full_name,
        requester_department=current_user.department,
    )


@router.get("/processes", response_model=list[ProcessSummary])
def list_processes(
    db: Session | None = Depends(get_sync_db),
    limit: int = 20,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ProcessSummary]:
    _ = current_user
    rows = list_recent_processes(db, limit=min(limit, 50))
    summaries: list[ProcessSummary] = []
    for row in rows:
        payload = row.process_json or {}
        activities = payload.get("activities") or []
        summaries.append(
            ProcessSummary(
                process_id=row.id,
                name=row.name,
                status=row.status,
                discovery_status=row.discovery_status,
                overall_confidence=row.overall_confidence,
                activity_count=len(activities),
                created_at=row.created_at.isoformat() if row.created_at else None,
            )
        )
    return summaries


@router.get("/processes/{process_id}", response_model=ProcessDetail)
def read_process(
    process_id: UUID,
    db: Session | None = Depends(get_sync_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ProcessDetail:
    _ = current_user
    row = get_process(db, process_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Process not found")
    tasks = list_process_tasks(db, process_id)
    if tasks:
        workflow = [
            WorkflowStep(
                order=task.sort_order,
                title=task.title,
                actor=task.actor,
                system=task.system,
                avg_duration=task.avg_duration,
                status=task.status,
                description=task.description,
            )
            for task in tasks
        ]
    else:
        activities = (row.process_json or {}).get("activities") or []
        workflow = [
            WorkflowStep(
                order=index,
                title=activity.get("name") or f"Step {index + 1}",
                actor=activity.get("actor"),
                system=activity.get("system"),
                avg_duration=activity.get("avg_duration"),
            )
            for index, activity in enumerate(activities)
        ]
    return ProcessDetail(
        process_id=row.id,
        name=row.name,
        status=row.status,
        discovery_status=row.discovery_status,
        overall_confidence=row.overall_confidence,
        workflow=workflow,
        process_json=row.process_json or {},
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.post(
    "/documents",
    response_model=DocumentIngestResponse,
    summary="Ingest a document into the tenant-scoped IR index",
)
def ingest_document(
    files: UploadFiles,
    document_type: Annotated[str | None, Form()] = None,
    source: Annotated[str, Form()] = "upload",
    version: Annotated[str, Form()] = "1",
    db: Session | None = Depends(get_sync_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DocumentIngestResponse:
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")
    if current_user.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant identity is required")
    from app.agents.agent1_discovery.ingest import content_sha256
    from app.agents.agent1_discovery.service import _buffer_upload

    upload = files[0]
    buffered = _buffer_upload(upload)
    digest = content_sha256(buffered.content)
    prior = get_document_corpus().get_by_hash(current_user.tenant_id, digest)
    document, chunks, _extracted = ingest_bytes(
        tenant_id=current_user.tenant_id,
        filename=buffered.filename,
        content=buffered.content,
        document_type=document_type,
        source=source,
        version=version,
        mime_type=getattr(upload, "content_type", None),
        db=db,
    )
    return DocumentIngestResponse(
        document_id=document.document_id,
        tenant_id=document.tenant_id,
        filename=document.filename,
        document_type=document.document_type,
        source=document.source,
        version=document.version,
        is_active=document.is_active,
        content_hash=document.content_hash,
        parse_status=document.parse_status,
        parse_failure=document.parse_failure,
        chunk_count=len(chunks),
        reused=prior is not None,
    )


@router.get("/documents/{document_id}")
def get_document(
    document_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant identity is required")
    document = get_document_corpus().get_document(current_user.tenant_id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "document_id": str(document.document_id),
        "tenant_id": str(document.tenant_id),
        "filename": document.filename,
        "document_type": document.document_type,
        "source": document.source,
        "version": document.version,
        "is_active": document.is_active,
        "content_hash": document.content_hash,
        "parse_status": document.parse_status,
        "parse_failure": document.parse_failure,
        "evidence_ref": document.evidence_ref,
        "uploaded_at": document.uploaded_at.isoformat(),
    }


@router.post("/search", response_model=list[SearchHit])
def search_documents(
    body: SearchRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[SearchHit]:
    if current_user.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant identity is required")
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    hits = get_document_corpus().search(
        tenant_id=current_user.tenant_id,
        query=body.query,
        top_k=min(max(body.top_k, 1), 50),
        document_id=body.document_id,
    )
    return [
        SearchHit(
            document_id=hit.document_id,
            chunk_id=hit.chunk_id,
            page=hit.page,
            score=hit.score,
            text=hit.text,
            snippet=hit.snippet,
            document_version=hit.document_version,
            filename=hit.filename,
            document_type=hit.document_type,
            source=hit.source,
            section=hit.section,
        )
        for hit in hits
    ]


@router.get("/evidence/{chunk_id}")
def get_evidence(
    chunk_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant identity is required")
    chunk = get_document_corpus().get_chunk(current_user.tenant_id, chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return {
        "chunk_id": str(chunk.chunk_id),
        "document_id": str(chunk.document_id),
        "tenant_id": str(chunk.tenant_id),
        "page": chunk.page,
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
        "document_version": chunk.document_version,
        "filename": chunk.filename,
        "document_type": chunk.document_type,
        "source": chunk.source,
        "section": chunk.section,
    }
