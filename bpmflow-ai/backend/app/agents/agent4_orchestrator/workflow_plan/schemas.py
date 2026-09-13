"""Pydantic records for Agent 4 WorkflowPlan (definition, not execution)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import WorkflowPlanStatus, WorkflowStepStatus, WorkflowStepType

UNRESOLVED_RESPONSIBLE_PERSON = "RESPONSIBLE_PERSON_NOT_RESOLVED"


class WorkflowEvidenceRef(BaseModel):
    """Pointer to existing evidence — never an invented evidence ID."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    document_id: UUID | None = None
    kind: str | None = None


class WorkflowPolicyRef(BaseModel):
    """Pointer to existing policy — never an invented policy ID."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str
    policy_version: str | None = None


class WorkflowStepRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    workflow_plan_id: UUID
    step_key: str
    sequence: int
    name: str
    description: str | None = None
    step_type: WorkflowStepType
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    responsible_employee_id: UUID | None = None
    responsible_resource_id: UUID | None = None
    responsible_role_id: UUID | None = None
    responsible_department_id: UUID | None = None
    assignment_unresolved: bool = False
    unresolved_reason: str | None = None
    depends_on_step_keys: list[str] = Field(default_factory=list)
    required_action: str | None = None
    required_tool_category: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected_outputs: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[WorkflowEvidenceRef] = Field(default_factory=list)
    policy_refs: list[WorkflowPolicyRef] = Field(default_factory=list)
    risk_level: str | None = None
    approval_required: bool = False
    approval_type: str | None = None
    recipient_employee_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("step_key")
    @classmethod
    def _step_key_stable(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("step_key is required")
        return text

    @field_validator("sequence")
    @classmethod
    def _sequence_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("sequence must be >= 1")
        return value


class WorkflowPlanRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    process_id: UUID
    version: int
    status: WorkflowPlanStatus = WorkflowPlanStatus.DRAFT
    created_by_agent: str = "agent4"
    source_process_context_schema_version: str | None = None
    source_process_context_ref: str | None = "process_context"
    steps: list[WorkflowStepRecord] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateWorkflowPlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_id: UUID
    source_process_context_schema_version: str | None = None
    source_process_context_ref: str | None = "process_context"


class CreateWorkflowStepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_key: str
    sequence: int
    name: str
    description: str | None = None
    step_type: WorkflowStepType
    responsible_employee_id: UUID | None = None
    responsible_resource_id: UUID | None = None
    responsible_role_id: UUID | None = None
    responsible_department_id: UUID | None = None
    assignment_unresolved: bool = False
    unresolved_reason: str | None = None
    depends_on_step_keys: list[str] = Field(default_factory=list)
    required_action: str | None = None
    required_tool_category: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected_outputs: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[WorkflowEvidenceRef] = Field(default_factory=list)
    policy_refs: list[WorkflowPolicyRef] = Field(default_factory=list)
    risk_level: str | None = None
    approval_required: bool = False
    approval_type: str | None = None
    recipient_employee_ids: list[UUID] = Field(default_factory=list)
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    step_key: str | None = None


class WorkflowPlanValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
