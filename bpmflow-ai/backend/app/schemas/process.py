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
    description: str | None = None


class ProcessResponse(BaseModel):
    """Process record exposed to API clients."""

    id: UUID
    name: str
    description: str | None = None
    process_type: str
    status: str
    current_stage: WorkflowStage
    version: int
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    # Execution / procurement evidence (PO drafts, last tool run, etc.).
    metadata_json: dict | None = None


class ProcessStartResponse(BaseModel):
    """Result of POST .../start. Discovery may be unavailable."""

    process: ProcessResponse
    success: bool
    message: str
    error_code: str | None = None
    error_message: str | None = None
    agent_response: dict | None = None


class ResourcePlanningRequest(BaseModel):
    """Payload for POST .../plan-resources (Agent 3 allocation via Agent 4).

    tenant_id/task_id are required because Agent 3's contract requires both.
    human_requirements/budget_requirements follow Agent 3's request schemas.
    """

    task_id: UUID
    tenant_id: UUID
    correlation_id: UUID | None = None
    human_requirements: dict | None = None
    budget_requirements: dict | None = None


class RiskReviewRequest(BaseModel):
    """Payload for POST .../risk-review. Mirrors RiskEvaluationContext fields."""

    task_id: UUID | None = None
    purchase_amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    required_evidence: list[str] = Field(default_factory=list)
    provided_evidence: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    requester_id: UUID | None = None
    approver_id: UUID | None = None
    unauthorized_action: bool = False
    budget_validation_failed: bool = False


class ExecuteWorkflowRequest(BaseModel):
    """Payload for POST .../execute (Agent 2 execution via Agent 4)."""

    task_id: UUID | None = None
    task_type: str = "EXECUTE_TASK"
    correlation_id: UUID | None = None
    parameters: dict = Field(default_factory=dict)


class AdvanceProcessRequest(BaseModel):
    """Payload for POST .../advance — autonomous stage chaining."""

    correlation_id: UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
    max_steps: int = Field(default=8, ge=1, le=20)
    reconcile_stale: bool = False
    invoice: Optional["InvoiceMatchingCompleteRequest"] = None
    resource_planning: ResourcePlanningRequest | None = None


class AdvanceProcessResponse(BaseModel):
    """Result of autonomous process advancement."""

    process: ProcessResponse
    advancement: dict


class InvoiceMatchingCompleteRequest(BaseModel):
    """Invoice evidence for deterministic matching at INVOICE_MATCHING.

    Completion requires a real match against expected purchase data stored on
    the process and/or provided as expected_* fields. A bare reference string
    alone cannot complete the process.
    """

    invoice_number: str | None = None
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = None
    vendor: str | None = None
    po_reference: str | None = None
    expected_po_reference: str | None = None
    expected_amount: float | None = Field(default=None, ge=0)
    expected_currency: str | None = None
    expected_vendor: str | None = None
    expected_invoice_number: str | None = None
    notes: str = ""
    # Legacy alias used by older clients — treated as notes only, not a match key.
    reference: str = ""


AdvanceProcessRequest.model_rebuild()
