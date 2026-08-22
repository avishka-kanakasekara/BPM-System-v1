"""API schemas for audit resources."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

from app.agents.agent4_orchestrator.audit_repository import AuditLogRecord


class AuditLogResponse(BaseModel):
    """Audit log row exposed to API clients."""

    id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    performed_by: Optional[UUID] = None
    old_values: Optional[dict[str, Any]] = None
    new_values: Optional[dict[str, Any]] = None
    timestamp: datetime


def audit_from_record(record: AuditLogRecord) -> AuditLogResponse:
    """Map a repository audit record to an API response schema."""
    return AuditLogResponse.model_validate(record.model_dump())
