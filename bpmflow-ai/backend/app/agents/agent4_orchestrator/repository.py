"""Process persistence for Agent 4 orchestration.

SQLAlchemy async sessions come from app.core.database.get_db when wired later.
Unit tests use InMemoryProcessRepository or a mocked session.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.process import Process

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


class InMemoryProcessRepository(ProcessRepository):
    """In-memory stand-in used by unit tests."""

    def __init__(self) -> None:
        self._stages: Dict[UUID, WorkflowStage] = {}
        self._history: List[ProcessStateTransition] = []

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
