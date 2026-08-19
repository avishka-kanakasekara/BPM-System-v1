"""Pydantic schemas for Agent 4 workflow state management."""

from uuid import UUID

from pydantic import BaseModel, Field

from .constants import WorkflowStage


class ProcessStateTransition(BaseModel):
    """A requested BPM workflow stage change for a process."""

    process_id: UUID
    from_stage: WorkflowStage
    to_stage: WorkflowStage
    reason: str = Field(min_length=1)
