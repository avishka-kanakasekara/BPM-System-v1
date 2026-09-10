"""Persistence for public.exceptions and related audit_logs events."""

from abc import ABC, abstractmethod
import asyncio
from datetime import datetime, timezone
from typing import Dict, List
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.supabase_rest import (
    rest_insert,
    rest_select,
    rest_update,
    supabase_rest_configured,
    use_supabase_rest_fallback,
)
from app.models.audit import AuditLog
from app.models.exception import ProcessException

from .constants import ExceptionSeverity, ExceptionStatus, ExceptionType
from .exceptions import BpmExceptionNotFoundError, DatabasePersistenceError
from .repository import AUDIT_ACTION_UPDATED, AUDIT_ENTITY_PROCESS
from .schemas import ExceptionRecord

AUDIT_ACTION_CREATED = "created"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def record_from_orm(row: ProcessException) -> ExceptionRecord:
    return ExceptionRecord(
        id=row.id,
        process_id=row.process_id,
        task_id=row.task_id,
        severity=ExceptionSeverity(row.severity),
        type=ExceptionType(row.type),
        description=row.description,
        status=ExceptionStatus(row.status),
        assigned_to=row.assigned_to,
        resolution_notes=row.resolution_notes,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


def record_from_rest(row: dict) -> ExceptionRecord:
    severity_raw = str(row.get("severity") or "medium")
    type_raw = str(row.get("type") or "system_error")
    status_raw = str(row.get("status") or "open")
    try:
        severity = ExceptionSeverity(severity_raw)
    except ValueError:
        severity = ExceptionSeverity.MEDIUM
    try:
        exception_type = ExceptionType(type_raw)
    except ValueError:
        exception_type = ExceptionType.SYSTEM_ERROR
    try:
        status = ExceptionStatus(status_raw)
    except ValueError:
        status = ExceptionStatus.OPEN
    return ExceptionRecord(
        id=UUID(str(row["id"])),
        process_id=UUID(str(row["process_id"])) if row.get("process_id") else None,
        task_id=UUID(str(row["task_id"])) if row.get("task_id") else None,
        severity=severity,
        type=exception_type,
        description=str(row.get("description") or "Exception"),
        status=status,
        assigned_to=UUID(str(row["assigned_to"])) if row.get("assigned_to") else None,
        resolution_notes=row.get("resolution_notes"),
        created_at=row["created_at"],
        resolved_at=row.get("resolved_at"),
    )


def _list_exceptions_rest(status: ExceptionStatus | None) -> List[ExceptionRecord]:
    params: dict[str, str] = {
        "select": "id,process_id,task_id,severity,type,description,status,assigned_to,resolution_notes,created_at,resolved_at",
        "order": "created_at.desc",
    }
    if status is not None:
        params["status"] = f"eq.{status.value}"
    return [record_from_rest(row) for row in rest_select("exceptions", params)]


def _get_exception_rest(exception_id: UUID) -> ExceptionRecord:
    rows = rest_select(
        "exceptions",
        {
            "id": f"eq.{exception_id}",
            "select": "id,process_id,task_id,severity,type,description,status,assigned_to,resolution_notes,created_at,resolved_at",
            "limit": "1",
        },
    )
    if not rows:
        raise BpmExceptionNotFoundError(exception_id)
    return record_from_rest(rows[0])


def _create_exception_rest(
    process_id: UUID | None,
    description: str,
    severity: ExceptionSeverity,
    exception_type: ExceptionType,
    task_id: UUID | None,
    assigned_to: UUID | None,
) -> ExceptionRecord:
    # task_id REFERENCES public.tasks — omit when the row does not exist yet
    # (Agent 2 failures often pass a client-generated task UUID).
    safe_task_id: UUID | None = None
    if task_id is not None:
        existing = rest_select(
            "tasks",
            {"id": f"eq.{task_id}", "select": "id", "limit": "1"},
        )
        if existing:
            safe_task_id = task_id

    row = rest_insert(
        "exceptions",
        {
            "process_id": str(process_id) if process_id else None,
            "task_id": str(safe_task_id) if safe_task_id else None,
            "severity": severity.value,
            "type": exception_type.value,
            "description": description,
            "status": ExceptionStatus.OPEN.value,
            "assigned_to": str(assigned_to) if assigned_to else None,
        },
    )
    rest_insert(
        "audit_logs",
        {
            "entity_type": AUDIT_ENTITY_PROCESS,
            "entity_id": str(process_id or row.get("id")),
            "action": AUDIT_ACTION_CREATED,
            "new_values": {
                "exception_id": row.get("id"),
                "status": ExceptionStatus.OPEN.value,
                "type": exception_type.value,
                "severity": severity.value,
            },
        },
    )
    return record_from_rest(row)


def _update_exception_rest(record: ExceptionRecord) -> ExceptionRecord:
    row = rest_update(
        "exceptions",
        {"id": f"eq.{record.id}"},
        {
            "process_id": str(record.process_id) if record.process_id else None,
            "task_id": str(record.task_id) if record.task_id else None,
            "severity": record.severity.value,
            "type": record.type.value,
            "description": record.description,
            "status": record.status.value,
            "assigned_to": str(record.assigned_to) if record.assigned_to else None,
            "resolution_notes": record.resolution_notes,
            "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
        },
    )
    if isinstance(row, dict) and row.get("id"):
        return record_from_rest(row)
    return _get_exception_rest(record.id)


class ExceptionRepository(ABC):
    """CRUD for BPM exceptions without owning process-stage rules."""

    @abstractmethod
    async def create_exception(
        self,
        process_id: UUID | None,
        description: str,
        severity: ExceptionSeverity,
        exception_type: ExceptionType,
        task_id: UUID | None = None,
        assigned_to: UUID | None = None,
    ) -> ExceptionRecord:
        """Insert an open exception and audit it."""

    @abstractmethod
    async def get_exception(self, exception_id: UUID) -> ExceptionRecord:
        """Load one exception by id."""

    @abstractmethod
    async def list_exceptions(
        self,
        status: ExceptionStatus | None = None,
    ) -> List[ExceptionRecord]:
        """Return exception rows, optionally filtered by status."""

    @abstractmethod
    async def update_exception(self, record: ExceptionRecord) -> ExceptionRecord:
        """Persist a full exception record."""

    @abstractmethod
    async def record_audit(
        self,
        process_id: UUID | None,
        exception_id: UUID,
        action: str,
        old_values: dict | None,
        new_values: dict | None,
        performed_by: UUID | None = None,
    ) -> None:
        """Write an audit_logs row for an exception lifecycle event."""

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class InMemoryExceptionRepository(ExceptionRepository):
    def __init__(self) -> None:
        self._records: Dict[UUID, ExceptionRecord] = {}
        self.audit_events: List[dict] = []

    async def create_exception(
        self,
        process_id: UUID | None,
        description: str,
        severity: ExceptionSeverity,
        exception_type: ExceptionType,
        task_id: UUID | None = None,
        assigned_to: UUID | None = None,
    ) -> ExceptionRecord:
        record = ExceptionRecord(
            id=uuid4(),
            process_id=process_id,
            task_id=task_id,
            severity=severity,
            type=exception_type,
            description=description,
            status=ExceptionStatus.OPEN,
            assigned_to=assigned_to,
            resolution_notes=None,
            created_at=utc_now(),
            resolved_at=None,
        )
        self._records[record.id] = record
        await self.record_audit(
            process_id,
            record.id,
            AUDIT_ACTION_CREATED,
            None,
            {
                "exception_id": str(record.id),
                "status": record.status.value,
                "type": record.type.value,
                "severity": record.severity.value,
            },
        )
        return record

    async def get_exception(self, exception_id: UUID) -> ExceptionRecord:
        if exception_id not in self._records:
            raise BpmExceptionNotFoundError(exception_id)
        return self._records[exception_id]

    async def list_exceptions(
        self,
        status: ExceptionStatus | None = None,
    ) -> List[ExceptionRecord]:
        records = list(self._records.values())
        if status is not None:
            records = [record for record in records if record.status is status]
        records.sort(key=lambda record: record.created_at, reverse=True)
        return records

    async def update_exception(self, record: ExceptionRecord) -> ExceptionRecord:
        if record.id not in self._records:
            raise BpmExceptionNotFoundError(record.id)
        self._records[record.id] = record
        return record

    async def record_audit(
        self,
        process_id: UUID | None,
        exception_id: UUID,
        action: str,
        old_values: dict | None,
        new_values: dict | None,
        performed_by: UUID | None = None,
    ) -> None:
        self.audit_events.append(
            {
                "entity_type": AUDIT_ENTITY_PROCESS,
                "entity_id": process_id or exception_id,
                "action": action,
                "performed_by": performed_by,
                "old_values": old_values,
                "new_values": new_values,
            }
        )


class SqlAlchemyExceptionRepository(ExceptionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _prefer_rest(self) -> bool:
        return use_supabase_rest_fallback()

    async def create_exception(
        self,
        process_id: UUID | None,
        description: str,
        severity: ExceptionSeverity,
        exception_type: ExceptionType,
        task_id: UUID | None = None,
        assigned_to: UUID | None = None,
    ) -> ExceptionRecord:
        if self._prefer_rest():
            return await asyncio.to_thread(
                _create_exception_rest,
                process_id,
                description,
                severity,
                exception_type,
                task_id,
                assigned_to,
            )
        created_at = utc_now()
        row = ProcessException(
            id=uuid4(),
            process_id=process_id,
            task_id=task_id,
            severity=severity.value,
            type=exception_type.value,
            description=description,
            status=ExceptionStatus.OPEN.value,
            assigned_to=assigned_to,
            resolution_notes=None,
            created_at=created_at,
            resolved_at=None,
        )
        try:
            self._session.add(row)
            await self.record_audit(
                process_id,
                row.id,
                AUDIT_ACTION_CREATED,
                None,
                {
                    "exception_id": str(row.id),
                    "status": ExceptionStatus.OPEN.value,
                    "type": exception_type.value,
                    "severity": severity.value,
                },
            )
            await self._session.flush()
        except Exception as exc:
            if supabase_rest_configured():
                try:
                    return await asyncio.to_thread(
                        _create_exception_rest,
                        process_id,
                        description,
                        severity,
                        exception_type,
                        task_id,
                        assigned_to,
                    )
                except Exception:
                    pass
            raise DatabasePersistenceError("Failed to create exception") from exc
        return record_from_orm(row)

    async def get_exception(self, exception_id: UUID) -> ExceptionRecord:
        if self._prefer_rest():
            return await asyncio.to_thread(_get_exception_rest, exception_id)
        try:
            row = await self._get_row(exception_id)
            return record_from_orm(row)
        except BpmExceptionNotFoundError:
            raise
        except Exception:
            if supabase_rest_configured():
                return await asyncio.to_thread(_get_exception_rest, exception_id)
            raise

    async def list_exceptions(
        self,
        status: ExceptionStatus | None = None,
    ) -> List[ExceptionRecord]:
        if self._prefer_rest():
            return await asyncio.to_thread(_list_exceptions_rest, status)
        try:
            stmt = select(ProcessException).order_by(ProcessException.created_at.desc())
            if status is not None:
                stmt = stmt.where(ProcessException.status == status.value)
            result = await self._session.execute(stmt)
            rows = result.scalars().all()
        except Exception as exc:
            if supabase_rest_configured():
                try:
                    return await asyncio.to_thread(_list_exceptions_rest, status)
                except Exception:
                    pass
            raise DatabasePersistenceError("Failed to list exceptions") from exc
        return [record_from_orm(row) for row in rows]

    async def update_exception(self, record: ExceptionRecord) -> ExceptionRecord:
        if self._prefer_rest():
            return await asyncio.to_thread(_update_exception_rest, record)
        try:
            row = await self._get_row(record.id)
            row.process_id = record.process_id
            row.task_id = record.task_id
            row.severity = record.severity.value
            row.type = record.type.value
            row.description = record.description
            row.status = record.status.value
            row.assigned_to = record.assigned_to
            row.resolution_notes = record.resolution_notes
            row.resolved_at = record.resolved_at
            await self._session.flush()
        except BpmExceptionNotFoundError:
            raise
        except Exception as exc:
            if supabase_rest_configured():
                try:
                    return await asyncio.to_thread(_update_exception_rest, record)
                except Exception:
                    pass
            raise DatabasePersistenceError("Failed to update exception") from exc
        return record_from_orm(row)

    async def record_audit(
        self,
        process_id: UUID | None,
        exception_id: UUID,
        action: str,
        old_values: dict | None,
        new_values: dict | None,
        performed_by: UUID | None = None,
    ) -> None:
        if self._prefer_rest():
            await asyncio.to_thread(
                rest_insert,
                "audit_logs",
                {
                    "entity_type": AUDIT_ENTITY_PROCESS,
                    "entity_id": str(process_id or exception_id),
                    "action": action,
                    "performed_by": str(performed_by) if performed_by else None,
                    "old_values": old_values,
                    "new_values": new_values,
                },
            )
            return
        try:
            self._session.add(
                AuditLog(
                    id=uuid4(),
                    entity_type=AUDIT_ENTITY_PROCESS,
                    entity_id=process_id or exception_id,
                    action=action,
                    performed_by=performed_by,
                    old_values=old_values,
                    new_values=new_values,
                    timestamp=utc_now(),
                )
            )
        except Exception as exc:
            if supabase_rest_configured():
                try:
                    await asyncio.to_thread(
                        rest_insert,
                        "audit_logs",
                        {
                            "entity_type": AUDIT_ENTITY_PROCESS,
                            "entity_id": str(process_id or exception_id),
                            "action": action,
                            "performed_by": str(performed_by) if performed_by else None,
                            "old_values": old_values,
                            "new_values": new_values,
                        },
                    )
                    return
                except Exception:
                    pass
            raise DatabasePersistenceError("Failed to record exception audit") from exc

    async def commit(self) -> None:
        if self._prefer_rest():
            return
        try:
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            raise DatabasePersistenceError("Failed to commit exception change") from exc

    async def rollback(self) -> None:
        if self._prefer_rest():
            return
        try:
            await self._session.rollback()
        except Exception as exc:
            raise DatabasePersistenceError("Failed to roll back exception change") from exc

    async def _get_row(self, exception_id: UUID) -> ProcessException:
        try:
            row = await self._session.get(ProcessException, exception_id)
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Failed to load exception {exception_id}"
            ) from exc
        if row is None:
            raise BpmExceptionNotFoundError(exception_id)
        return row
