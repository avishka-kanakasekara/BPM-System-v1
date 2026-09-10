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
from app.agents.agent1_discovery.service import run_discovery
from app.core.config import settings
from app.core.database import get_sync_db
from app.core.security import get_current_user
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
    _ = current_user  # authenticated identity required; discovery is informational
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
    return run_discovery(files, db, process_id=process_id)


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
