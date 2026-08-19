"""BPM workflow controller for Agent 4.

Stage rules come only from StateMachine. Persistence is delegated to a
ProcessRepository (in-memory for tests, SQLAlchemy for PostgreSQL).
"""

from typing import List
from uuid import UUID

from .constants import WorkflowStage
from .exceptions import DatabasePersistenceError, ProcessNotFoundError
from .repository import InMemoryProcessRepository, ProcessRepository
from .schemas import ProcessStateTransition
from .state_machine import InvalidTransitionError, StateMachine


class OrchestratorService:
    """Central BPM workflow controller.

    Flow: repository current_stage -> StateMachine validation -> persist + audit.
    """

    def __init__(
        self,
        state_machine: StateMachine | None = None,
        repository: ProcessRepository | None = None,
    ) -> None:
        self._state_machine = state_machine or StateMachine()
        self._repository = repository or InMemoryProcessRepository()

    async def create_process(
        self,
        process_id: UUID,
        initial_stage: WorkflowStage = WorkflowStage.DRAFT,
    ) -> WorkflowStage:
        """Register a process and return its current stage.

        Defaults to DRAFT. In-memory only unless the repository implements create.
        Does not apply a StateMachine transition on create.
        """
        return await self._repository.create_process(process_id, initial_stage)

    async def get_current_stage(self, process_id: UUID) -> WorkflowStage:
        """Return the current workflow stage for a process."""
        return await self._load_stage(process_id)

    async def can_move(self, process_id: UUID, next_stage: WorkflowStage) -> bool:
        """Return True if the process may move to next_stage."""
        current_stage = await self._load_stage(process_id)
        return self._state_machine.can_transition(current_stage, next_stage)

    async def move_process(
        self,
        process_id: UUID,
        next_stage: WorkflowStage,
        reason: str,
    ) -> ProcessStateTransition:
        """Validate and apply a stage change.

        Raises:
            ProcessNotFoundError: if process_id is unknown.
            InvalidTransitionError: if StateMachine rejects the move.
            DatabasePersistenceError: if persistence fails after a valid move.
        """
        current_stage = await self._load_stage(process_id)
        self._state_machine.transition(current_stage, next_stage)

        try:
            await self._repository.update_process_stage(process_id, next_stage)
            result = await self._repository.record_transition(
                process_id,
                current_stage,
                next_stage,
                reason,
            )
            await self._repository.commit()
        except (ProcessNotFoundError, InvalidTransitionError):
            await self._safe_rollback()
            raise
        except DatabasePersistenceError:
            await self._safe_rollback()
            raise
        except Exception as exc:
            await self._safe_rollback()
            raise DatabasePersistenceError(
                f"Failed to persist transition for process {process_id}"
            ) from exc

        return result

    async def get_allowed_next_stages(self, process_id: UUID) -> List[WorkflowStage]:
        """Return stages the process may move to from its current stage."""
        current_stage = await self._load_stage(process_id)
        return self._state_machine.get_allowed_next_stages(current_stage)

    async def get_transition_history(
        self,
        process_id: UUID | None = None,
    ) -> List[ProcessStateTransition]:
        """Return recorded transitions, optionally filtered by process_id."""
        return await self._repository.get_transition_history(process_id)

    async def _load_stage(self, process_id: UUID) -> WorkflowStage:
        try:
            return await self._repository.get_process_stage(process_id)
        except (ProcessNotFoundError, DatabasePersistenceError):
            raise
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Failed to read stage for process {process_id}"
            ) from exc

    async def _safe_rollback(self) -> None:
        try:
            await self._repository.rollback()
        except DatabasePersistenceError:
            raise
        except Exception as exc:
            raise DatabasePersistenceError(
                "Failed to roll back process stage change"
            ) from exc
