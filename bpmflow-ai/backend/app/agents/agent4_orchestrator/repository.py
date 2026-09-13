"""Process persistence for Agent 4 orchestration.

SQLAlchemy async sessions come from app.core.database.get_db when wired later.
Unit tests use InMemoryProcessRepository or a mocked session.
When the Postgres pooler is unreachable, list/get/insert fall back to Supabase REST.
"""

import asyncio
import json
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
from app.models.process import Process
from app.schemas.process import ProcessResponse

from .constants import WorkflowStage
from .exceptions import (
    DatabasePersistenceError,
    ProcessAlreadyExistsError,
    ProcessNotFoundError,
)
from .schemas import ProcessStateTransition

AUDIT_ENTITY_PROCESS = "process"
AUDIT_ACTION_UPDATED = "updated"


class ProcessRepository(ABC):
    """Persistence for process stages and transition audit events."""

    @abstractmethod
    async def get_process_stage(self, process_id: UUID) -> WorkflowStage:
        """Return the stored current_stage for a process."""

    @abstractmethod
    async def update_process_stage(
        self,
        process_id: UUID,
        new_stage: WorkflowStage,
    ) -> None:
        """Persist a new current_stage."""

    @abstractmethod
    async def record_transition(
        self,
        process_id: UUID,
        from_stage: WorkflowStage,
        to_stage: WorkflowStage,
        reason: str,
    ) -> ProcessStateTransition:
        """Record a stage change (in-memory history or audit_logs)."""

    async def create_process(
        self,
        process_id: UUID,
        initial_stage: WorkflowStage = WorkflowStage.DRAFT,
    ) -> WorkflowStage:
        """Register a process for tests. SQL repositories do not insert rows."""
        raise NotImplementedError(
            "Process rows must already exist in the database; "
            "use InMemoryProcessRepository in tests."
        )

    async def get_transition_history(
        self,
        process_id: UUID | None = None,
    ) -> list[ProcessStateTransition]:
        """Return recorded transitions. Default is empty."""
        return []

    async def commit(self) -> None:
        """Commit a unit of work. No-op for in-memory storage."""
        return None

    async def rollback(self) -> None:
        """Roll back a unit of work. No-op for in-memory storage."""
        return None

    async def insert_process(
        self,
        name: str,
        process_type: str,
        description: str | None = None,
        created_by: UUID | None = None,
    ) -> ProcessResponse:
        """Insert a public.processes row at status=draft, current_stage=DRAFT."""
        raise NotImplementedError

    async def get_process(self, process_id: UUID) -> ProcessResponse:
        """Return a process record for API responses."""
        raise NotImplementedError

    async def list_processes(self) -> list[ProcessResponse]:
        """Return process records for API list responses."""
        raise NotImplementedError


class InMemoryProcessRepository(ProcessRepository):
    """In-memory stand-in used by unit tests."""

    def __init__(self) -> None:
        self._stages: dict[UUID, WorkflowStage] = {}
        self._history: list[ProcessStateTransition] = []
        self._records: dict[UUID, ProcessResponse] = {}

    async def create_process(
        self,
        process_id: UUID,
        initial_stage: WorkflowStage = WorkflowStage.DRAFT,
    ) -> WorkflowStage:
        if process_id in self._stages:
            raise ProcessAlreadyExistsError(process_id)
        self._stages[process_id] = initial_stage
        return initial_stage

    async def get_process_stage(self, process_id: UUID) -> WorkflowStage:
        if process_id not in self._stages:
            raise ProcessNotFoundError(process_id)
        return self._stages[process_id]

    async def update_process_stage(
        self,
        process_id: UUID,
        new_stage: WorkflowStage,
    ) -> None:
        if process_id not in self._stages:
            raise ProcessNotFoundError(process_id)
        self._stages[process_id] = new_stage
        record = self._records.get(process_id)
        if record is not None:
            self._records[process_id] = record.model_copy(
                update={
                    "current_stage": new_stage,
                    "updated_at": datetime.now(UTC),
                }
            )

    async def record_transition(
        self,
        process_id: UUID,
        from_stage: WorkflowStage,
        to_stage: WorkflowStage,
        reason: str,
    ) -> ProcessStateTransition:
        item = ProcessStateTransition(
            process_id=process_id,
            from_stage=from_stage,
            to_stage=to_stage,
            reason=reason,
        )
        self._history.append(item)
        return item

    async def get_transition_history(
        self,
        process_id: UUID | None = None,
    ) -> list[ProcessStateTransition]:
        if process_id is None:
            return list(self._history)
        return [item for item in self._history if item.process_id == process_id]

    async def insert_process(
        self,
        name: str,
        process_type: str,
        description: str | None = None,
        created_by: UUID | None = None,
    ) -> ProcessResponse:
        now = datetime.now(UTC)
        process_id = uuid4()
        record = ProcessResponse(
            id=process_id,
            name=name,
            description=description,
            process_type=process_type,
            status="draft",
            current_stage=WorkflowStage.DRAFT,
            version=1,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self._records[process_id] = record
        self._stages[process_id] = WorkflowStage.DRAFT
        return record

    async def get_process(self, process_id: UUID) -> ProcessResponse:
        record = self._records.get(process_id)
        if record is None:
            raise ProcessNotFoundError(process_id)
        stage = self._stages.get(process_id, record.current_stage)
        return record.model_copy(update={"current_stage": stage})

    async def list_processes(self) -> list[ProcessResponse]:
        items = []
        for process_id, record in self._records.items():
            stage = self._stages.get(process_id, record.current_stage)
            items.append(record.model_copy(update={"current_stage": stage}))
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items


class SqlAlchemyProcessRepository(ProcessRepository):
    """PostgreSQL persistence via SQLAlchemy async sessions.

    Prefer the injected session when Postgres is reachable. When the sync
    engine probe has already determined Postgres is down and Supabase REST is
    configured, use REST first to avoid long asyncpg timeouts.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _prefer_rest(self) -> bool:
        return use_supabase_rest_fallback()

    async def get_process_stage(self, process_id: UUID) -> WorkflowStage:
        if self._prefer_rest():
            process = await asyncio.to_thread(_get_process_rest, process_id)
            return process.current_stage
        try:
            process = await self._get_process(process_id)
            return WorkflowStage(process.current_stage)
        except ProcessNotFoundError:
            raise
        except DatabasePersistenceError:
            if supabase_rest_configured():
                try:
                    process = await asyncio.to_thread(_get_process_rest, process_id)
                    return process.current_stage
                except ProcessNotFoundError:
                    raise
                except Exception:
                    pass
            raise

    async def update_process_stage(
        self,
        process_id: UUID,
        new_stage: WorkflowStage,
    ) -> None:
        if self._prefer_rest():
            await asyncio.to_thread(_update_process_stage_rest, process_id, new_stage)
            return
        try:
            process = await self._get_process(process_id)
            process.current_stage = new_stage.value
            process.updated_at = datetime.now(UTC)
        except ProcessNotFoundError:
            raise
        except DatabasePersistenceError:
            if supabase_rest_configured():
                try:
                    await asyncio.to_thread(_update_process_stage_rest, process_id, new_stage)
                    return
                except ProcessNotFoundError:
                    raise
                except Exception:
                    pass
            raise

    async def record_transition(
        self,
        process_id: UUID,
        from_stage: WorkflowStage,
        to_stage: WorkflowStage,
        reason: str,
    ) -> ProcessStateTransition:
        transition = ProcessStateTransition(
            process_id=process_id,
            from_stage=from_stage,
            to_stage=to_stage,
            reason=reason,
        )
        if self._prefer_rest():
            await asyncio.to_thread(
                _record_transition_rest,
                process_id,
                from_stage,
                to_stage,
                reason,
            )
            return transition
        try:
            from app.core.audit_writer import bpm_audit_orm

            self._session.add(
                bpm_audit_orm(
                    entity_type=AUDIT_ENTITY_PROCESS,
                    entity_id=process_id,
                    action=AUDIT_ACTION_UPDATED,
                    old_values={"current_stage": from_stage.value},
                    new_values={"current_stage": to_stage.value, "reason": reason},
                )
            )
        except Exception as exc:
            if supabase_rest_configured():
                await asyncio.to_thread(
                    _record_transition_rest,
                    process_id,
                    from_stage,
                    to_stage,
                    reason,
                )
                return transition
            raise DatabasePersistenceError(
                f"Failed to record audit log for process {process_id}"
            ) from exc
        return transition

    async def commit(self) -> None:
        if self._prefer_rest():
            return
        try:
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            raise DatabasePersistenceError(
                "Failed to commit process stage change"
            ) from exc

    async def rollback(self) -> None:
        if self._prefer_rest():
            return
        try:
            await self._session.rollback()
        except Exception as exc:
            raise DatabasePersistenceError(
                "Failed to roll back process stage change"
            ) from exc

    async def insert_process(
        self,
        name: str,
        process_type: str,
        description: str | None = None,
        created_by: UUID | None = None,
    ) -> ProcessResponse:
        if self._prefer_rest():
            return await asyncio.to_thread(
                _insert_process_rest,
                name,
                process_type,
                description,
                created_by,
            )
        try:
            now = datetime.now(UTC)
            process = Process(
                id=uuid4(),
                name=name,
                description=description,
                process_type=process_type,
                status="draft",
                version=1,
                created_by=created_by,
                created_at=now,
                updated_at=now,
                current_stage=WorkflowStage.DRAFT.value,
                process_json={},
            )
            self._session.add(process)
            await self._session.commit()
            await self._session.refresh(process)
            return process_from_orm(process)
        except Exception as exc:
            await self._session.rollback()
            if supabase_rest_configured():
                try:
                    return await asyncio.to_thread(
                        _insert_process_rest,
                        name,
                        process_type,
                        description,
                        created_by,
                    )
                except Exception:
                    pass
            raise DatabasePersistenceError("Failed to create process") from exc

    async def get_process(self, process_id: UUID) -> ProcessResponse:
        if self._prefer_rest():
            return await asyncio.to_thread(_get_process_rest, process_id)
        try:
            return await self._get_process_mapped(process_id)
        except ProcessNotFoundError:
            raise
        except DatabasePersistenceError as exc:
            if supabase_rest_configured():
                try:
                    return await asyncio.to_thread(_get_process_rest, process_id)
                except ProcessNotFoundError:
                    raise
                except Exception:
                    pass
            raise DatabasePersistenceError(
                f"Failed to load process {process_id}"
            ) from exc

    async def list_processes(self) -> list[ProcessResponse]:
        if self._prefer_rest():
            return await asyncio.to_thread(_list_processes_rest)
        try:
            result = await self._session.execute(
                select(Process).order_by(Process.created_at.desc())
            )
            rows = result.scalars().all()
            return [process_from_orm(row) for row in rows]
        except Exception as exc:
            if supabase_rest_configured():
                try:
                    return await asyncio.to_thread(_list_processes_rest)
                except Exception:
                    pass
            raise DatabasePersistenceError("Failed to list processes") from exc

    async def _get_process(self, process_id: UUID) -> Process:
        try:
            result = await self._session.execute(
                select(Process).where(Process.id == process_id)
            )
            process = result.scalar_one_or_none()
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Failed to load process {process_id}"
            ) from exc
        if process is None:
            raise ProcessNotFoundError(process_id)
        return process

    async def _get_process_mapped(self, process_id: UUID) -> ProcessResponse:
        process = await self._get_process(process_id)
        return process_from_orm(process)


def process_from_orm(process: Process) -> ProcessResponse:
    """Map a Process ORM row to an API schema without exposing SQLAlchemy."""
    return ProcessResponse(
        id=process.id,
        name=process.name,
        description=process.description,
        process_type=process.process_type,
        status=process.status,
        current_stage=WorkflowStage(process.current_stage),
        version=process.version if process.version is not None else 1,
        created_by=process.created_by,
        created_at=process.created_at,
        updated_at=process.updated_at,
        metadata_json=getattr(process, "metadata_json", None) or None,
    )


def _merge_discovery_metadata(row: dict) -> dict | None:
    """Unify metadata_json, process_json column, and legacy description JSON."""
    meta: dict = {}
    raw_meta = row.get("metadata_json")
    if isinstance(raw_meta, dict):
        meta.update(raw_meta)
    process_json = row.get("process_json")
    if isinstance(process_json, dict) and process_json:
        meta.setdefault("process_json", process_json)
    description = row.get("description")
    if isinstance(description, str) and description.strip().startswith("{"):
        try:
            parsed = json.loads(description)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            if isinstance(parsed.get("process_json"), dict):
                meta.setdefault("process_json", parsed["process_json"])
            for key in ("discovery_status", "overall_confidence", "trace_id", "documents"):
                if key in parsed and key not in meta:
                    meta[key] = parsed[key]
    return meta or None


def process_from_rest(row: dict) -> ProcessResponse:
    """Map a PostgREST processes row to ProcessResponse."""
    return ProcessResponse.model_validate(
        {
            "id": row["id"],
            "name": row["name"],
            "description": row.get("description"),
            "process_type": row.get("process_type") or "GENERAL",
            "status": row.get("status") or "draft",
            "current_stage": row.get("current_stage") or WorkflowStage.DRAFT.value,
            "version": row.get("version") if row.get("version") is not None else 1,
            "created_by": row.get("created_by"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "metadata_json": _merge_discovery_metadata(row),
        }
    )


def _list_processes_rest() -> list[ProcessResponse]:
    rows = rest_select(
        "processes",
        {
            "select": "id,name,description,process_type,status,version,created_by,created_at,updated_at,current_stage,metadata_json,process_json",
            "order": "created_at.desc",
        },
    )
    return [process_from_rest(row) for row in rows]


def _get_process_rest(process_id: UUID) -> ProcessResponse:
    rows = rest_select(
        "processes",
        {
            "id": f"eq.{process_id}",
            "select": "id,name,description,process_type,status,version,created_by,created_at,updated_at,current_stage,metadata_json,process_json",
            "limit": "1",
        },
    )
    if not rows:
        raise ProcessNotFoundError(process_id)
    return process_from_rest(rows[0])


def _insert_process_rest(
    name: str,
    process_type: str,
    description: str | None,
    created_by: UUID | None,
) -> ProcessResponse:
    row = rest_insert(
        "processes",
        {
            "name": name,
            "description": description,
            "process_type": process_type,
            "status": "draft",
            "version": 1,
            "created_by": str(created_by) if created_by else None,
            "current_stage": WorkflowStage.DRAFT.value,
            "process_json": {},
        },
    )
    return process_from_rest(row)


def _update_process_stage_rest(process_id: UUID, new_stage: WorkflowStage) -> None:
    _get_process_rest(process_id)
    rest_update(
        "processes",
        {"id": f"eq.{process_id}"},
        {
            "current_stage": new_stage.value,
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )


def _record_transition_rest(
    process_id: UUID,
    from_stage: WorkflowStage,
    to_stage: WorkflowStage,
    reason: str,
) -> None:
    from app.core.audit_writer import write_bpm_audit_rest

    write_bpm_audit_rest(
        entity_type=AUDIT_ENTITY_PROCESS,
        entity_id=process_id,
        action=AUDIT_ACTION_UPDATED,
        old_values={"current_stage": from_stage.value},
        new_values={"current_stage": to_stage.value, "reason": reason},
    )
