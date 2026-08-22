"""AUDIT endpoints for read-only access to public.audit_logs."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agents.agent4_orchestrator.audit_repository import (
    DEFAULT_AUDIT_LIMIT,
    MAX_AUDIT_LIMIT,
    AuditRepository,
)
from app.agents.agent4_orchestrator.exceptions import DatabasePersistenceError
from app.api.v1.deps import get_audit_repository
from app.core.security import get_current_user
from app.schemas.audit import AuditLogResponse, audit_from_record
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/audit", tags=["audit"])

DATABASE_DETAIL = "Database unavailable"
INTERNAL_DETAIL = "Internal server error"


def _database_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=DATABASE_DETAIL,
    )


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    entity_type: str | None = Query(default=None),
    entity_id: UUID | None = Query(default=None),
    limit: int = Query(default=DEFAULT_AUDIT_LIMIT, ge=1, le=MAX_AUDIT_LIMIT),
    offset: int = Query(default=0, ge=0),
    repository: AuditRepository = Depends(get_audit_repository),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[AuditLogResponse]:
    """Return audit trail rows, newest first, with optional filters and pagination."""
    try:
        records = await repository.list_audit_logs(
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
            offset=offset,
        )
    except DatabasePersistenceError as exc:
        raise _database_error() from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_DETAIL,
        ) from exc
    return [audit_from_record(record) for record in records]
