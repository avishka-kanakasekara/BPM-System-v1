"""API schemas for exception resources."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.agents.agent4_orchestrator.constants import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
)
from app.agents.agent4_orchestrator.schemas import ExceptionRecord


class ExceptionResponse(BaseModel):
    """Exception record exposed to API clients."""

    id: UUID
    process_id: UUID | None = None
    task_id: UUID | None = None
    tenant_id: UUID | None = None
    workflow_plan_id: UUID | None = None
    workflow_step_id: UUID | None = None
    exception_code: str | None = None
    title: str | None = None
    severity: ExceptionSeverity
    type: ExceptionType
    description: str = Field(min_length=1)
    status: ExceptionStatus
    assigned_to: UUID | None = None
    assigned_employee_id: UUID | None = None
    resolved_by_employee_id: UUID | None = None
    source_agent: str | None = None
    source_operation: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)
    resolution_notes: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    resolved_at: datetime | None = None


class ExceptionResolveRequest(BaseModel):
    """Payload for resolving an exception."""

    resolution_notes: str = Field(min_length=1)


class ExceptionRetryRequest(BaseModel):
    """Payload for retrying an exception."""

    notes: str | None = None


class ExceptionFailRequest(BaseModel):
    """Payload for terminal failure of an exception."""

    resolution_notes: str = Field(min_length=1)


class ExceptionActionResponse(BaseModel):
    """Outcome of resolve, retry, or fail actions."""

    exception: ExceptionResponse


def exception_from_record(record: ExceptionRecord) -> ExceptionResponse:
    """Map an Agent 4 exception record to an API schema."""
    return ExceptionResponse.model_validate(record.model_dump())


def action_from_record(record: ExceptionRecord) -> ExceptionActionResponse:
    """Wrap an updated exception record as an action response."""
    return ExceptionActionResponse(exception=exception_from_record(record))
