"""API schemas for exception resources."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.agents.agent4_orchestrator.constants import ExceptionSeverity, ExceptionStatus, ExceptionType
from app.agents.agent4_orchestrator.schemas import ExceptionRecord


class ExceptionResponse(BaseModel):
    """Exception record exposed to API clients."""

    id: UUID
    process_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    severity: ExceptionSeverity
    type: ExceptionType
    description: str = Field(min_length=1)
    status: ExceptionStatus
    assigned_to: Optional[UUID] = None
    resolution_notes: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None


class ExceptionResolveRequest(BaseModel):
    """Payload for resolving an exception."""

    resolution_notes: str = Field(min_length=1)


class ExceptionRetryRequest(BaseModel):
    """Payload for retrying an exception."""

    notes: Optional[str] = None


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
