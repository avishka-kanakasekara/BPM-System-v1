"""API schemas for process resources."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.agents.agent4_orchestrator.constants import WorkflowStage


class ProcessCreate(BaseModel):
    """Payload to insert a public.processes row."""

    name: str = Field(min_length=1)
    process_type: str = Field(min_length=1)
    description: Optional[str] = None


class ProcessResponse(BaseModel):
    """Process record exposed to API clients."""

    id: UUID
    name: str
    description: Optional[str] = None
    process_type: str
    status: str
    current_stage: WorkflowStage
    version: int
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class ProcessStartResponse(BaseModel):
    """Result of POST .../start. Discovery may be unavailable."""

    process: ProcessResponse
    success: bool
    message: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
