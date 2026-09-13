"""Persistence for public.exceptions and related audit_logs events."""

import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime
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
from app.models.exception import ProcessException

from .constants import ExceptionSeverity, ExceptionStatus, ExceptionType, exception_type_from_code
from .exceptions import BpmExceptionNotFoundError, DatabasePersistenceError
from .repository import AUDIT_ENTITY_PROCESS
from .schemas import ExceptionRecord

AUDIT_ACTION_CREATED = "created"
_REST_SELECT = (
    "id,process_id,task_id,tenant_id,workflow_plan_id,workflow_step_id,exception_code,title,"
    "severity,type,description,status,assigned_to,assigned_employee_id,resolved_by_employee_id,"
    "source_agent,source_operation,evidence_refs,details,resolution_notes,created_at,updated_at,resolved_at"
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _uuid_or_none(value) -> UUID | None:
    if value in (None, ""):
        return None
    return value if isinstance(value, UUID) else UUID(str(value))


def _list_or_empty(value) -> list:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _dict_or_empty(value) -> dict:
    return value if isinstance(value, dict) else {}


def record_from_orm(row: ProcessException) -> ExceptionRecord:
    exception_type = exception_type_from_code(row.type)
    code = getattr(row, "exception_code", None) or exception_type.value
    return ExceptionRecord(
        id=row.id,
        process_id=row.process_id,
        task_id=row.task_id,
        tenant_id=getattr(row, "tenant_id", None),
        workflow_plan_id=getattr(row, "workflow_plan_id", None),
        workflow_step_id=getattr(row, "workflow_step_id", None),
        exception_code=code,
        title=getattr(row, "title", None),
        severity=ExceptionSeverity(row.severity),
        type=exception_type,
        description=row.description,
        status=ExceptionStatus(row.status),
        assigned_to=row.assigned_to,
        assigned_employee_id=getattr(row, "assigned_employee_id", None) or row.assigned_to,
        resolved_by_employee_id=getattr(row, "resolved_by_employee_id", None),
        source_agent=getattr(row, "source_agent", None),
        source_operation=getattr(row, "source_operation", None),
        evidence_refs=_list_or_empty(getattr(row, "evidence_refs", None)),
        details=_dict_or_empty(getattr(row, "details", None)),
        resolution_notes=row.resolution_notes,
        created_at=row.created_at,
        updated_at=getattr(row, "updated_at", None),
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
    exception_type = exception_type_from_code(type_raw)
    return ExceptionRecord(
        id=UUID(str(row["id"])),
        process_id=UUID(str(row["process_id"])) if row.get("process_id") else None,
        task_id=UUID(str(row["task_id"])) if row.get("task_id") else None,
        tenant_id=_uuid_or_none(row.get("tenant_id")),
        workflow_plan_id=_uuid_or_none(row.get("workflow_plan_id")),
        workflow_step_id=_uuid_or_none(row.get("workflow_step_id")),
        exception_code=str(row.get("exception_code") or exception_type.value),
        title=row.get("title"),
        severity=severity,
        type=exception_type,
        description=str(row.get("description") or "Exception"),
        status=status,
        assigned_to=UUID(str(row["assigned_to"])) if row.get("assigned_to") else None,
        assigned_employee_id=_uuid_or_none(row.get("assigned_employee_id"))
        or (UUID(str(row["assigned_to"])) if row.get("assigned_to") else None),
        resolved_by_employee_id=_uuid_or_none(row.get("resolved_by_employee_id")),
        source_agent=row.get("source_agent"),
        source_operation=row.get("source_operation"),
        evidence_refs=_list_or_empty(row.get("evidence_refs")),
        details=_dict_or_empty(row.get("details")),
        resolution_notes=row.get("resolution_notes"),
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
        resolved_at=row.get("resolved_at"),
    )


def _list_exceptions_rest(status: ExceptionStatus | None) -> list[ExceptionRecord]:
    params: dict[str, str] = {
        "select": _REST_SELECT,
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
            "select": _REST_SELECT,
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
    extra: dict | None = None,
) -> ExceptionRecord:
    extra = extra or {}
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

    payload = {
        "process_id": str(process_id) if process_id else None,
        "task_id": str(safe_task_id) if safe_task_id else None,
        "severity": severity.value,
        "type": exception_type.value,
        "description": description,
        "status": ExceptionStatus.OPEN.value,
        "assigned_to": str(assigned_to) if assigned_to else None,
        "exception_code": extra.get("exception_code") or exception_type.value,
        "title": extra.get("title") or description[:200],
        "source_agent": extra.get("source_agent"),
        "source_operation": extra.get("source_operation"),
        "evidence_refs": extra.get("evidence_refs") or [],
        "details": extra.get("details") or {},
    }
    if extra.get("tenant_id"):
        payload["tenant_id"] = str(extra["tenant_id"])
    if extra.get("workflow_plan_id"):
        payload["workflow_plan_id"] = str(extra["workflow_plan_id"])
    if extra.get("workflow_step_id"):
        payload["workflow_step_id"] = str(extra["workflow_step_id"])
    if extra.get("assigned_employee_id"):
        payload["assigned_employee_id"] = str(extra["assigned_employee_id"])
    row = rest_insert("exceptions", payload)
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
            "assigned_employee_id": str(record.assigned_employee_id) if record.assigned_employee_id else None,
            "resolved_by_employee_id": str(record.resolved_by_employee_id) if record.resolved_by_employee_id else None,
            "exception_code": record.exception_code or record.type.value,
            "title": record.title,
            "source_agent": record.source_agent,
            "source_operation": record.source_operation,
            "evidence_refs": record.evidence_refs,
            "details": record.details,
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
        **extra,
    ) -> ExceptionRecord:
        """Insert an open exception and audit it."""

    @abstractmethod
    async def get_exception(self, exception_id: UUID) -> ExceptionRecord:
        """Load one exception by id."""

    @abstractmethod
    async def list_exceptions(
        self,
        status: ExceptionStatus | None = None,
        *,
        tenant_id: UUID | None = None,
        process_id: UUID | None = None,
    ) -> list[ExceptionRecord]:
        """Return exception rows, optionally filtered by status/tenant/process."""

    async def find_open_duplicate(
        self,
        *,
        process_id: UUID | None,
        exception_code: str,
        workflow_step_id: UUID | None = None,
        invoice_id: str | None = None,
        execution_event_id: str | None = None,
    ) -> ExceptionRecord | None:
        if process_id is None or not exception_code:
            return None
        records = await self.list_exceptions(process_id=process_id)
        for row in records:
            if row.status not in {ExceptionStatus.OPEN, ExceptionStatus.IN_PROGRESS}:
                continue
            if (row.exception_code or row.type.value) != exception_code:
                continue
            if workflow_step_id is not None and row.workflow_step_id not in {None, workflow_step_id}:
                continue
            details = row.details or {}
            if invoice_id:
                stored = str(details.get("invoice_id") or "")
                if stored and stored != invoice_id:
                    continue
                return row
            if execution_event_id:
                stored_event = str(details.get("execution_event_id") or "")
                if stored_event and stored_event != execution_event_id:
                    continue
                return row
            return row
        return None

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
        self._records: dict[UUID, ExceptionRecord] = {}
        self.audit_events: list[dict] = []

    async def create_exception(
        self,
        process_id: UUID | None,
        description: str,
        severity: ExceptionSeverity,
        exception_type: ExceptionType,
        task_id: UUID | None = None,
        assigned_to: UUID | None = None,
        **extra,
    ) -> ExceptionRecord:
        now = utc_now()
        exception_code = extra.get("exception_code") or exception_type.value
        assigned_employee_id = extra.get("assigned_employee_id") or assigned_to
        record = ExceptionRecord(
            id=uuid4(),
            process_id=process_id,
            task_id=task_id,
            tenant_id=extra.get("tenant_id"),
            workflow_plan_id=extra.get("workflow_plan_id"),
            workflow_step_id=extra.get("workflow_step_id"),
            exception_code=exception_code,
            title=extra.get("title") or description[:200],
            severity=severity,
            type=exception_type,
            description=description,
            status=ExceptionStatus.OPEN,
            assigned_to=assigned_to,
            assigned_employee_id=assigned_employee_id,
            source_agent=extra.get("source_agent"),
            source_operation=extra.get("source_operation"),
            evidence_refs=list(extra.get("evidence_refs") or []),
            details=dict(extra.get("details") or {}),
            resolution_notes=None,
            created_at=now,
            updated_at=now,
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
                "exception_code": record.exception_code,
                "severity": record.severity.value,
                "tenant_id": str(record.tenant_id) if record.tenant_id else None,
                "process_id": str(record.process_id) if record.process_id else None,
                "workflow_step_id": str(record.workflow_step_id) if record.workflow_step_id else None,
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
        *,
        tenant_id: UUID | None = None,
        process_id: UUID | None = None,
    ) -> list[ExceptionRecord]:
        records = list(self._records.values())
        if status is not None:
            records = [record for record in records if record.status is status]
        if tenant_id is not None:
            records = [record for record in records if record.tenant_id == tenant_id]
        if process_id is not None:
            records = [record for record in records if record.process_id == process_id]
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
        **extra,
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
                extra,
            )
        created_at = utc_now()
        exception_code = extra.get("exception_code") or exception_type.value
        row = ProcessException(
            id=uuid4(),
            process_id=process_id,
            task_id=task_id,
            tenant_id=extra.get("tenant_id"),
            workflow_plan_id=extra.get("workflow_plan_id"),
            workflow_step_id=extra.get("workflow_step_id"),
            exception_code=exception_code,
            title=extra.get("title") or description[:200],
            severity=severity.value,
            type=exception_type.value,
            description=description,
            status=ExceptionStatus.OPEN.value,
            assigned_to=assigned_to,
            assigned_employee_id=extra.get("assigned_employee_id") or assigned_to,
            source_agent=extra.get("source_agent"),
            source_operation=extra.get("source_operation"),
            evidence_refs=list(extra.get("evidence_refs") or []),
            details=dict(extra.get("details") or {}),
            resolution_notes=None,
            created_at=created_at,
            updated_at=created_at,
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
                        extra,
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
        *,
        tenant_id: UUID | None = None,
        process_id: UUID | None = None,
    ) -> list[ExceptionRecord]:
        if self._prefer_rest():
            return await asyncio.to_thread(_list_exceptions_rest, status)
        try:
            stmt = select(ProcessException).order_by(ProcessException.created_at.desc())
            if status is not None:
                stmt = stmt.where(ProcessException.status == status.value)
            if tenant_id is not None:
                stmt = stmt.where(ProcessException.tenant_id == tenant_id)
            if process_id is not None:
                stmt = stmt.where(ProcessException.process_id == process_id)
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
            row.tenant_id = record.tenant_id
            row.workflow_plan_id = record.workflow_plan_id
            row.workflow_step_id = record.workflow_step_id
            row.exception_code = record.exception_code
            row.title = record.title
            row.assigned_employee_id = record.assigned_employee_id
            row.resolved_by_employee_id = record.resolved_by_employee_id
            row.source_agent = record.source_agent
            row.source_operation = record.source_operation
            row.evidence_refs = list(record.evidence_refs or [])
            row.details = dict(record.details or {})
            row.updated_at = utc_now()
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
        from app.core.audit_writer import write_bpm_audit

        entity_id = process_id or exception_id
        try:
            await write_bpm_audit(
                self._session if not self._prefer_rest() else None,
                entity_type=AUDIT_ENTITY_PROCESS,
                entity_id=entity_id,
                action=action,
                old_values=old_values,
                new_values=new_values,
                performed_by=performed_by,
                prefer_rest=self._prefer_rest(),
            )
        except Exception as exc:
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
