"""Process persistence for Agent 4 orchestration.

SQLAlchemy async sessions come from app.core.database.get_db when wired later.
Unit tests use InMemoryProcessRepository or a mocked session.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
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
    ) -> List[ProcessStateTransition]:
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

    async def list_processes(self) -> List[ProcessResponse]:
        """Return process records for API list responses."""
        raise NotImplementedError


class InMemoryProcessRepository(ProcessRepository):
    """In-memory stand-in used by unit tests."""

    def __init__(self) -> None:
        self._stages: Dict[UUID, WorkflowStage] = {}
        self._history: List[ProcessStateTransition] = []
        self._records: Dict[UUID, ProcessResponse] = {}

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
                    "updated_at": datetime.now(timezone.utc),
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
    ) -> List[ProcessStateTransition]:
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
        now = datetime.now(timezone.utc)
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

    async def list_processes(self) -> List[ProcessResponse]:
        items = []
        for process_id, record in self._records.items():
            stage = self._stages.get(process_id, record.current_stage)
            items.append(record.model_copy(update={"current_stage": stage}))
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items


class SqlAlchemyProcessRepository(ProcessRepository):
    """PostgreSQL persistence via SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_process_stage(self, process_id: UUID) -> WorkflowStage:
        process = await self._get_process(process_id)
        return WorkflowStage(process.current_stage)

    async def update_process_stage(
        self,
        process_id: UUID,
        new_stage: WorkflowStage,
    ) -> None:
        process = await self._get_process(process_id)
        process.current_stage = new_stage.value
        process.updated_at = datetime.now(timezone.utc)

    async def record_transition(
        self,
        process_id: UUID,
        from_stage: WorkflowStage,
        to_stage: WorkflowStage,
        reason: str,
    ) -> ProcessStateTransition:
        try:
            self._session.add(
                AuditLog(
                    id=uuid4(),
                    entity_type=AUDIT_ENTITY_PROCESS,
                    entity_id=process_id,
                    action=AUDIT_ACTION_UPDATED,
                    performed_by=None,
                    old_values={"current_stage": from_stage.value},
                    new_values={
                        "current_stage": to_stage.value,
                        "reason": reason,
                    },
                    timestamp=datetime.now(timezone.utc),
                )
            )
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Failed to record audit log for process {process_id}"
            ) from exc
        return ProcessStateTransition(
            process_id=process_id,
            from_stage=from_stage,
            to_stage=to_stage,
            reason=reason,
        )

    async def commit(self) -> None:
        try:
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            raise DatabasePersistenceError(
                "Failed to commit process stage change"
            ) from exc

    async def rollback(self) -> None:
        try:
            await self._session.rollback()
        except Exception as exc:
            raise DatabasePersistenceError(
                "Failed to roll back process stage change"
            ) from exc

    async def _get_process(self, process_id: UUID) -> Process:
        try:
            process = await self._session.get(Process, process_id)
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Failed to load process {process_id}"
            ) from exc
        if process is None:
            raise ProcessNotFoundError(process_id)
        return process

    async def insert_process(
        self,
        name: str,
        process_type: str,
        description: str | None = None,
        created_by: UUID | None = None,
    ) -> ProcessResponse:
        now = datetime.now(timezone.utc)
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
        )
        try:
            self._session.add(process)
            await self._session.commit()
            await self._session.refresh(process)
        except Exception as exc:
            await self._session.rollback()
            raise DatabasePersistenceError("Failed to create process") from exc
        return process_from_orm(process)

    async def get_process(self, process_id: UUID) -> ProcessResponse:
        process = await self._get_process(process_id)
        return process_from_orm(process)

    async def list_processes(self) -> List[ProcessResponse]:
        try:
            result = await self._session.execute(
                select(Process).order_by(Process.created_at.desc())
            )
            rows = result.scalars().all()
        except Exception as exc:
            raise DatabasePersistenceError("Failed to list processes") from exc
        return [process_from_orm(row) for row in rows]


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
    )
