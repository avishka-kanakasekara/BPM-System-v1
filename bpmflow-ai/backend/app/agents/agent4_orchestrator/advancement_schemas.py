"""Schemas for the Agent 4 process advancement engine."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from .constants import WorkflowStage
from .schemas import WorkflowResult


class AdvancementRunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    WAITING_HUMAN = "WAITING_HUMAN"
    WAITING_INPUT = "WAITING_INPUT"
    FAILED = "FAILED"


class AutonomousAction(BaseModel):
    """One autonomous step taken by the advancement engine."""

    stage: WorkflowStage
    action: str
    guardrail: str
    success: bool
    message: str
    correlation_id: UUID
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class AdvancementRunRecord(BaseModel):
    id: UUID
    process_id: UUID
    correlation_id: UUID
    idempotency_key: str
    tenant_id: UUID | None = None
    performed_by: UUID | None = None
    task_id: UUID | None = None
    from_stage: WorkflowStage
    current_stage: WorkflowStage
    status: AdvancementRunStatus
    steps: list[AutonomousAction] = Field(default_factory=list)
    result_json: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class AdvancementResult(BaseModel):
    """Outcome of POST /processes/{id}/advance."""

    process_id: UUID
    run_id: UUID
    correlation_id: UUID
    idempotency_key: str
    status: AdvancementRunStatus
    from_stage: WorkflowStage
    current_stage: WorkflowStage
    steps_taken: int
    autonomous_actions: list[AutonomousAction] = Field(default_factory=list)
    waiting_for: str | None = None
    last_step: WorkflowResult | None = None
    message: str
    error_code: str | None = None
    error_message: str | None = None
    human_approval_required: bool = False
    replayed: bool = False
