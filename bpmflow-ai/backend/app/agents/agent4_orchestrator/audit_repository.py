"""Read-only persistence for public.audit_logs.

Write paths remain in process, approval, and exception repositories.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

from .exceptions import DatabasePersistenceError

DEFAULT_AUDIT_LIMIT = 50
MAX_AUDIT_LIMIT = 100


class AuditLogRecord(BaseModel):
    """One audit_logs row for API and test use."""

    id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    performed_by: Optional[UUID] = None
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    timestamp: datetime


def audit_from_orm(row: AuditLog) -> AuditLogRecord:
    return AuditLogRecord(
        id=row.id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        action=row.action,
        performed_by=row.performed_by,
        old_values=row.old_values,
        new_values=row.new_values,
        timestamp=row.timestamp,
    )


class AuditRepository(ABC):
    """Read-only access to audit trail rows."""

    @abstractmethod
    async def list_audit_logs(
        self,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        limit: int = DEFAULT_AUDIT_LIMIT,
        offset: int = 0,
    ) -> List[AuditLogRecord]:
        """Return audit rows newest first, with bounded pagination."""


class InMemoryAuditRepository(AuditRepository):
    """In-memory stand-in for API tests."""

    def __init__(self) -> None:
        self._records: List[AuditLogRecord] = []

    def add_record(self, record: AuditLogRecord) -> None:
        self._records.append(record)

    async def list_audit_logs(
        self,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        limit: int = DEFAULT_AUDIT_LIMIT,
        offset: int = 0,
    ) -> List[AuditLogRecord]:
        records = list(self._records)
        if entity_type is not None:
            records = [row for row in records if row.entity_type == entity_type]
        if entity_id is not None:
            records = [row for row in records if row.entity_id == entity_id]
        records.sort(key=lambda row: row.timestamp, reverse=True)
        return records[offset : offset + limit]


class SqlAlchemyAuditRepository(AuditRepository):
    """PostgreSQL read access for audit_logs via async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_audit_logs(
        self,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        limit: int = DEFAULT_AUDIT_LIMIT,
        offset: int = 0,
    ) -> List[AuditLogRecord]:
        bounded_limit = min(max(limit, 1), MAX_AUDIT_LIMIT)
        bounded_offset = max(offset, 0)
        try:
            stmt = select(AuditLog).order_by(AuditLog.timestamp.desc())
            if entity_type is not None:
                stmt = stmt.where(AuditLog.entity_type == entity_type)
            if entity_id is not None:
                stmt = stmt.where(AuditLog.entity_id == entity_id)
            stmt = stmt.limit(bounded_limit).offset(bounded_offset)
            result = await self._session.execute(stmt)
            rows = result.scalars().all()
        except Exception as exc:
            raise DatabasePersistenceError("Failed to list audit logs") from exc
        return [audit_from_orm(row) for row in rows]
