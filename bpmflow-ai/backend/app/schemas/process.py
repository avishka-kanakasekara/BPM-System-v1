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
    agent_response: Optional[dict] = None


class ResourcePlanningRequest(BaseModel):
    """Payload for POST .../plan-resources (Agent 3 allocation via Agent 4).

    tenant_id/task_id are required because Agent 3's contract requires both.
    human_requirements/budget_requirements follow Agent 3's request schemas.
    """

    task_id: UUID
    tenant_id: UUID
    correlation_id: Optional[UUID] = None
    human_requirements: Optional[dict] = None
    budget_requirements: Optional[dict] = None


class RiskReviewRequest(BaseModel):
    """Payload for POST .../risk-review. Mirrors RiskEvaluationContext fields."""

    task_id: Optional[UUID] = None
    purchase_amount: Optional[float] = Field(default=None, ge=0)
    required_evidence: list[str] = Field(default_factory=list)
    provided_evidence: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    requester_id: Optional[UUID] = None
    approver_id: Optional[UUID] = None
    unauthorized_action: bool = False
    budget_validation_failed: bool = False


class ExecuteWorkflowRequest(BaseModel):
    """Payload for POST .../execute (Agent 2 execution via Agent 4)."""

    task_id: Optional[UUID] = None
    task_type: str = "EXECUTE_TASK"
    correlation_id: Optional[UUID] = None
    parameters: dict = Field(default_factory=dict)


class InvoiceMatchingCompleteRequest(BaseModel):
    """Explicit closure of INVOICE_MATCHING (no automated matching exists)."""

    reference: str = ""
