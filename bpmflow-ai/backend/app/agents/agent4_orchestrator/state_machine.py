"""Deterministic BPM workflow state machine for Agent 4."""

from typing import Dict, FrozenSet, List

from .constants import WorkflowStage


class InvalidTransitionError(ValueError):
    """Raised when a BPM workflow transition is not explicitly allowed."""

    def __init__(self, current_stage: WorkflowStage, next_stage: WorkflowStage) -> None:
        self.current_stage = current_stage
        self.next_stage = next_stage
        super().__init__(
            f"Invalid workflow transition: {current_stage.value} → {next_stage.value}"
        )


ALLOWED_TRANSITIONS: Dict[WorkflowStage, FrozenSet[WorkflowStage]] = {
    WorkflowStage.DRAFT: frozenset({WorkflowStage.DISCOVERING}),
    WorkflowStage.DISCOVERING: frozenset({WorkflowStage.RESOURCE_PLANNING}),
    WorkflowStage.RESOURCE_PLANNING: frozenset({WorkflowStage.RISK_REVIEW}),
    WorkflowStage.RISK_REVIEW: frozenset(
        {
            WorkflowStage.AWAITING_HUMAN_APPROVAL,
            WorkflowStage.WORKFLOW_EXECUTION,
        }
    ),
    WorkflowStage.AWAITING_HUMAN_APPROVAL: frozenset(
        {
            WorkflowStage.WORKFLOW_EXECUTION,
            WorkflowStage.EXCEPTION,
        }
    ),
    WorkflowStage.WORKFLOW_EXECUTION: frozenset(
        {
            WorkflowStage.INVOICE_MATCHING,
            WorkflowStage.EXCEPTION,
        }
    ),
    WorkflowStage.INVOICE_MATCHING: frozenset(
        {
            WorkflowStage.COMPLETED,
            WorkflowStage.EXCEPTION,
        }
    ),
    WorkflowStage.EXCEPTION: frozenset(
        {
            WorkflowStage.DISCOVERING,
            WorkflowStage.COMPLETED,
        }
    ),
    WorkflowStage.COMPLETED: frozenset(),
}


class StateMachine:
    """Deterministic BPM stage transitions. No LLM involvement."""

    def can_transition(
        self,
        current_stage: WorkflowStage,
        next_stage: WorkflowStage,
    ) -> bool:
        """Return True if current_stage → next_stage is explicitly allowed."""
        return next_stage in ALLOWED_TRANSITIONS.get(current_stage, frozenset())

    def transition(
        self,
        current_stage: WorkflowStage,
        next_stage: WorkflowStage,
    ) -> WorkflowStage:
        """Apply an allowed transition and return next_stage.

        Raises:
            InvalidTransitionError: if the transition is not in the allowed map.
        """
        if not self.can_transition(current_stage, next_stage):
            raise InvalidTransitionError(current_stage, next_stage)
        return next_stage

    def get_allowed_next_stages(self, current_stage: WorkflowStage) -> List[WorkflowStage]:
        """Return the stages that may follow current_stage."""
        return list(ALLOWED_TRANSITIONS.get(current_stage, frozenset()))
