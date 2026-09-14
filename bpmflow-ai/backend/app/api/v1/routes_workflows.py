"""Authenticated tenant-scoped WorkflowPlan APIs. Agent 4 definition only."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.agents.agent4_orchestrator.exceptions import ProcessNotFoundError
from app.agents.agent4_orchestrator.workflow_plan.exceptions import (
    CrossTenantWorkflowError,
    PlanNotMutableError,
    WorkflowPlanError,
    WorkflowPlanNotFoundError,
    WorkflowStepNotFoundError,
)
from app.agents.agent4_orchestrator.workflow_plan.schemas import (
    CreateWorkflowPlanInput,
    CreateWorkflowStepInput,
    WorkflowPlanRecord,
    WorkflowPlanValidationResult,
    WorkflowStepRecord,
)
from app.agents.agent4_orchestrator.workflow_plan.service import WorkflowPlanService
from app.agents.agent2_execution.workflow_step.exceptions import WorkflowStepExecutionError
from app.agents.agent2_execution.workflow_step.schemas import (
    WorkflowStepExecutionRequest,
    WorkflowStepExecutionResult,
)
from app.api.v1.deps import get_workflow_plan_service, get_workflow_step_executor
from app.core.security import get_current_user, require_roles
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _require_tenant(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context is required for workflow operations",
        )
    return user.tenant_id


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkflowPlanNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow plan not found")
    if isinstance(exc, ProcessNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process not found")
    if isinstance(exc, WorkflowStepNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow step not found")
    if isinstance(exc, CrossTenantWorkflowError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.as_dict())
    if isinstance(exc, PlanNotMutableError | WorkflowPlanError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.as_dict())
    raise exc


@router.post("", response_model=WorkflowPlanRecord, status_code=status.HTTP_201_CREATED)
async def create_workflow_plan(
    payload: CreateWorkflowPlanInput,
    current_user: CurrentUser = Depends(get_current_user),
    service: WorkflowPlanService = Depends(get_workflow_plan_service),
) -> WorkflowPlanRecord:
    tenant_id = _require_tenant(current_user)
    try:
        return await service.create_draft(payload, tenant_id=tenant_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{workflow_plan_id}", response_model=WorkflowPlanRecord)
async def get_workflow_plan(
    workflow_plan_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: WorkflowPlanService = Depends(get_workflow_plan_service),
) -> WorkflowPlanRecord:
    tenant_id = _require_tenant(current_user)
    try:
        return await service.get_plan(workflow_plan_id, tenant_id=tenant_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{workflow_plan_id}/steps", response_model=list[WorkflowStepRecord])
async def list_workflow_steps(
    workflow_plan_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: WorkflowPlanService = Depends(get_workflow_plan_service),
) -> list[WorkflowStepRecord]:
    tenant_id = _require_tenant(current_user)
    try:
        return await service.list_steps(workflow_plan_id, tenant_id=tenant_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{workflow_plan_id}/steps", response_model=WorkflowStepRecord, status_code=status.HTTP_201_CREATED)
async def add_workflow_step(
    workflow_plan_id: UUID,
    payload: CreateWorkflowStepInput,
    current_user: CurrentUser = Depends(get_current_user),
    service: WorkflowPlanService = Depends(get_workflow_plan_service),
) -> WorkflowStepRecord:
    tenant_id = _require_tenant(current_user)
    try:
        return await service.add_step(workflow_plan_id, payload, tenant_id=tenant_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{workflow_plan_id}/validate", response_model=WorkflowPlanValidationResult)
async def validate_workflow_plan(
    workflow_plan_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: WorkflowPlanService = Depends(get_workflow_plan_service),
) -> WorkflowPlanValidationResult:
    tenant_id = _require_tenant(current_user)
    try:
        return await service.validate(workflow_plan_id, tenant_id=tenant_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{workflow_plan_id}/activate", response_model=WorkflowPlanRecord)
async def activate_workflow_plan(
    workflow_plan_id: UUID,
    current_user: CurrentUser = Depends(require_roles("approver", "admin")),
    service: WorkflowPlanService = Depends(get_workflow_plan_service),
) -> WorkflowPlanRecord:
    tenant_id = _require_tenant(current_user)
    try:
        return await service.activate(workflow_plan_id, tenant_id=tenant_id)
    except Exception as exc:
        raise _map_error(exc) from exc


class ExecuteWorkflowStepBody(BaseModel):
    process_id: UUID
    process_context_ref: UUID | None = None
    trace_id: str | None = None
    idempotency_key: str | None = None
    parameters: dict = Field(default_factory=dict)
    authorization_state: str | None = None


@router.post(
    "/{workflow_plan_id}/steps/{workflow_step_id}/execute",
    response_model=WorkflowStepExecutionResult,
)
async def execute_workflow_step(
    workflow_plan_id: UUID,
    workflow_step_id: UUID,
    payload: ExecuteWorkflowStepBody,
    current_user: CurrentUser = Depends(get_current_user),
    executor=Depends(get_workflow_step_executor),
) -> WorkflowStepExecutionResult:
    tenant_id = _require_tenant(current_user)
    try:
        return await executor.execute_one_step(
            WorkflowStepExecutionRequest(
                process_id=payload.process_id,
                workflow_plan_id=workflow_plan_id,
                workflow_step_id=workflow_step_id,
                process_context_ref=payload.process_context_ref,
                authorization_state="PENDING",
                trace_id=payload.trace_id,
                idempotency_key=payload.idempotency_key,
                caller_parameters=dict(payload.parameters),
            ),
            tenant_id=tenant_id,
        )
    except WorkflowStepExecutionError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.as_dict()) from exc
    except Exception as exc:
        raise _map_error(exc) from exc
