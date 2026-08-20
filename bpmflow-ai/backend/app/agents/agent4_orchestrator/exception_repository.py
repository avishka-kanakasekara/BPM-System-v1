"""Persistence for public.exceptions and related audit_logs events."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def create_exception(
        self,
        process_id: UUID | None,
        description: str,
        severity: ExceptionSeverity,
        exception_type: ExceptionType,
        task_id: UUID | None = None,
        assigned_to: UUID | None = None,
    ) -> ExceptionRecord:
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
            raise DatabasePersistenceError("Failed to create exception") from exc
        return record_from_orm(row)

    async def get_exception(self, exception_id: UUID) -> ExceptionRecord:
        row = await self._get_row(exception_id)
        return record_from_orm(row)

    async def list_exceptions(
        self,
        status: ExceptionStatus | None = None,
    ) -> List[ExceptionRecord]:
        try:
            stmt = select(ProcessException).order_by(ProcessException.created_at.desc())
            if status is not None:
                stmt = stmt.where(ProcessException.status == status.value)
            result = await self._session.execute(stmt)
            rows = result.scalars().all()
        except Exception as exc:
            raise DatabasePersistenceError("Failed to list exceptions") from exc
        return [record_from_orm(row) for row in rows]

    async def update_exception(self, record: ExceptionRecord) -> ExceptionRecord:
        row = await self._get_row(record.id)
        try:
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
        except Exception as exc:
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
            raise DatabasePersistenceError("Failed to record exception audit") from exc

    async def commit(self) -> None:
        try:
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            raise DatabasePersistenceError("Failed to commit exception change") from exc

    async def rollback(self) -> None:
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
