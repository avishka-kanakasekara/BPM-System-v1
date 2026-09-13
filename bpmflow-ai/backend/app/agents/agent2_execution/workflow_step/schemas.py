"""One-step WorkflowStep execution request/result. Tool name is not authoritative."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStepExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_id: UUID
    workflow_plan_id: UUID
    workflow_step_id: UUID
    process_context_ref: UUID | None = None
    authorization_state: str = "AUTHORIZED"
    trace_id: str | None = None
    idempotency_key: str | None = None
    caller_parameters: dict[str, Any] = Field(default_factory=dict)


class WorkflowStepExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_status: str
    workflow_plan_id: UUID
    workflow_step_id: UUID
    process_id: UUID
    action_code: str | None = None
    tool_name: str | None = None
    implementation_key: str | None = None
    receipt_id: UUID | None = None
    step_status: str
    result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    trace_id: str | None = None
    idempotency_key: str | None = None
    duplicate: bool = False
