"""Planning result schemas. Execution readiness is distinct from structural validity."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .schemas import WorkflowPlanRecord, WorkflowStepRecord


class PlanningIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    blocking: bool = True
    step_key: str | None = None


class WorkflowPlanningResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_id: UUID
    tenant_id: UUID
    workflow_plan_id: UUID | None = None
    version: int | None = None
    status: str | None = None
    execution_ready: bool = False
    structurally_valid: bool = False
    steps: list[WorkflowStepRecord] = Field(default_factory=list)
    issues: list[PlanningIssue] = Field(default_factory=list)
    plan: WorkflowPlanRecord | None = None
    allocations: dict[str, Any] = Field(default_factory=dict)

    @property
    def blocking_errors(self) -> list[PlanningIssue]:
        return [item for item in self.issues if item.blocking]
