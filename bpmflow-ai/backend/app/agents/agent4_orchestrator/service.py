"""In-memory BPM workflow controller for Agent 4."""

from typing import Dict, List
from uuid import UUID

from .constants import WorkflowStage
from .schemas import ProcessStateTransition
from .state_machine import InvalidTransitionError, StateMachine


class ProcessNotFoundError(KeyError):
    """Raised when a process_id is not tracked by the orchestrator."""

    def __init__(self, process_id: UUID) -> None:
        self.process_id = process_id
        super().__init__(f"Unknown process: {process_id}")


class ProcessAlreadyExistsError(ValueError):
    """Raised when create_process is called for an existing process_id."""

    def __init__(self, process_id: UUID) -> None:
        self.process_id = process_id
        super().__init__(f"Process already exists: {process_id}")


class OrchestratorService:
    """Central in-memory BPM workflow controller.

    Stage transition rules come only from StateMachine.
    Persistence is in-memory so this can be unit-tested without FastAPI or Supabase.
    """

    def __init__(self, state_machine: StateMachine | None = None) -> None:
        self._state_machine = state_machine or StateMachine()
        self._stages: Dict[UUID, WorkflowStage] = {}
        self._history: List[ProcessStateTransition] = []

    def create_process(
        self,
        process_id: UUID,
        initial_stage: WorkflowStage = WorkflowStage.DRAFT,
    ) -> WorkflowStage:
        """Register a process and return its current stage.

        Defaults to DRAFT. Does not apply a StateMachine transition on create.
        """
        if process_id in self._stages:
            raise ProcessAlreadyExistsError(process_id)
        self._stages[process_id] = initial_stage
        return initial_stage

    def get_current_stage(self, process_id: UUID) -> WorkflowStage:
        """Return the current workflow stage for a process."""
        return self._require_stage(process_id)

    def can_move(self, process_id: UUID, next_stage: WorkflowStage) -> bool:
        """Return True if the process may move to next_stage."""
        current_stage = self._require_stage(process_id)
        return self._state_machine.can_transition(current_stage, next_stage)

    def move_process(
        self,
        process_id: UUID,
        next_stage: WorkflowStage,
        reason: str,
    ) -> ProcessStateTransition:
        """Validate and apply a stage change.

        Raises:
            ProcessNotFoundError: if process_id is unknown.
            InvalidTransitionError: if StateMachine rejects the move.
        """
        current_stage = self._require_stage(process_id)
        self._state_machine.transition(current_stage, next_stage)

        result = ProcessStateTransition(
            process_id=process_id,
            from_stage=current_stage,
            to_stage=next_stage,
            reason=reason,
        )
        self._stages[process_id] = next_stage
        self._history.append(result)
        return result

    def get_allowed_next_stages(self, process_id: UUID) -> List[WorkflowStage]:
        """Return stages the process may move to from its current stage."""
        current_stage = self._require_stage(process_id)
        return self._state_machine.get_allowed_next_stages(current_stage)

    def get_transition_history(
        self,
        process_id: UUID | None = None,
    ) -> List[ProcessStateTransition]:
        """Return recorded transitions, optionally filtered by process_id."""
        if process_id is None:
            return list(self._history)
        return [item for item in self._history if item.process_id == process_id]

    def _require_stage(self, process_id: UUID) -> WorkflowStage:
        if process_id not in self._stages:
            raise ProcessNotFoundError(process_id)
        return self._stages[process_id]
