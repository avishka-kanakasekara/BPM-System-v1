"""PROCESS endpoints — full pipeline orchestration through Agent 4.

Every stage change goes through OrchestratorService/StateMachine. The routes
here only trigger workflow methods; they never write current_stage directly.
"""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.agent4_orchestrator.exceptions import (
    DatabasePersistenceError,
    ProcessNotFoundError,
)
from app.agents.agent4_orchestrator.repository import ProcessRepository
from app.agents.agent4_orchestrator.schemas import RiskEvaluationContext, WorkflowResult
from app.agents.agent4_orchestrator.state_machine import InvalidTransitionError
from app.agents.agent4_orchestrator.workflow import Agent4Workflow
from app.api.v1.deps import get_agent4_workflow, get_process_repository
from app.core.security import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.process import (
    ExecuteWorkflowRequest,
    InvoiceMatchingCompleteRequest,
    ProcessCreate,
    ProcessResponse,
    ProcessStartResponse,
    ResourcePlanningRequest,
    RiskReviewRequest,
)

router = APIRouter(prefix="/processes", tags=["processes"])

NOT_FOUND_DETAIL = "Process not found"
DATABASE_DETAIL = "Database unavailable"
INTERNAL_DETAIL = "Internal server error"


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)


def _database_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=DATABASE_DETAIL,
    )


@router.get("", response_model=list[ProcessResponse])
async def list_processes(
    repository: ProcessRepository = Depends(get_process_repository),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ProcessResponse]:
    try:
        return await repository.list_processes()
    except DatabasePersistenceError as exc:
        raise _database_error() from exc


@router.post("", response_model=ProcessResponse, status_code=status.HTTP_201_CREATED)
async def create_process(
    payload: ProcessCreate,
    repository: ProcessRepository = Depends(get_process_repository),
    current_user: CurrentUser = Depends(get_current_user),
) -> ProcessResponse:
    """Insert a public.processes row. Does not call Agent 1."""
    try:
        return await repository.insert_process(
            name=payload.name,
            process_type=payload.process_type,
            description=payload.description,
            created_by=current_user.id,
        )
    except DatabasePersistenceError as exc:
        raise _database_error() from exc


@router.get("/{process_id}", response_model=ProcessResponse)
async def get_process(
    process_id: UUID,
    repository: ProcessRepository = Depends(get_process_repository),
    current_user: CurrentUser = Depends(get_current_user),
) -> ProcessResponse:
    try:
        return await repository.get_process(process_id)
    except ProcessNotFoundError as exc:
        raise _not_found() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc


@router.post("/{process_id}/start", response_model=ProcessStartResponse)
async def start_process(
    process_id: UUID,
    repository: ProcessRepository = Depends(get_process_repository),
    workflow: Agent4Workflow = Depends(get_agent4_workflow),
    current_user: CurrentUser = Depends(get_current_user),
) -> ProcessStartResponse:
    """Move DRAFT → DISCOVERING via the StateMachine, then attempt Agent 1.

    Agent 1 unavailability is a controlled response, not HTTP 500.
    """
    try:
        await repository.get_process(process_id)
        result = await workflow.start_existing_process(process_id)
        process = await repository.get_process(process_id)
    except ProcessNotFoundError as exc:
        raise _not_found() from exc
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invalid workflow transition",
        ) from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_DETAIL,
        ) from exc

    return ProcessStartResponse(
        process=process,
        success=result.success,
        message=result.message,
        error_code=result.error_code,
        error_message=result.error_message,
        agent_response=result.agent_response,
    )


def _invalid_transition() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Invalid workflow transition",
    )


@router.post("/{process_id}/plan-resources", response_model=WorkflowResult)
async def plan_resources(
    process_id: UUID,
    payload: ResourcePlanningRequest,
    workflow: Agent4Workflow = Depends(get_agent4_workflow),
    current_user: CurrentUser = Depends(get_current_user),
) -> WorkflowResult:
    """DISCOVERING → RESOURCE_PLANNING, call real Agent 3, then → RISK_REVIEW.

    tenant_id on the Agent 3 message comes from the verified JWT
    app_metadata when present. The request-body tenant_id is only a
    fallback for callers whose token has no tenant claim (tests / local).
    Body tenant_id never overrides a JWT tenant.
    """
    tenant_id = current_user.tenant_id or payload.tenant_id
    try:
        return await workflow.run_resource_planning(
            process_id,
            payload={
                "human_requirements": payload.human_requirements,
                "budget_requirements": payload.budget_requirements,
            },
            task_id=payload.task_id,
            tenant_id=tenant_id,
            correlation_id=payload.correlation_id,
        )
    except ProcessNotFoundError as exc:
        raise _not_found() from exc
    except InvalidTransitionError as exc:
        raise _invalid_transition() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc


@router.post("/{process_id}/risk-review", response_model=WorkflowResult)
async def risk_review(
    process_id: UUID,
    payload: RiskReviewRequest,
    workflow: Agent4Workflow = Depends(get_agent4_workflow),
    current_user: CurrentUser = Depends(get_current_user),
) -> WorkflowResult:
    """Run the deterministic risk engine at RISK_REVIEW.

    Opens a human approval gate (→ AWAITING_HUMAN_APPROVAL) or, with no
    approval-level findings, advances to WORKFLOW_EXECUTION.
    """
    context = RiskEvaluationContext(
        purchase_amount=(
            Decimal(str(payload.purchase_amount))
            if payload.purchase_amount is not None
            else None
        ),
        required_evidence=payload.required_evidence,
        provided_evidence=payload.provided_evidence,
        confidence=(
            Decimal(str(payload.confidence)) if payload.confidence is not None else None
        ),
        requester_id=payload.requester_id,
        approver_id=payload.approver_id,
        unauthorized_action=payload.unauthorized_action,
        budget_validation_failed=payload.budget_validation_failed,
    )
    try:
        return await workflow.handle_risk(
            process_id,
            context,
            task_id=payload.task_id,
            requested_by=current_user.id,
        )
    except ProcessNotFoundError as exc:
        raise _not_found() from exc
    except InvalidTransitionError as exc:
        raise _invalid_transition() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc


@router.post("/{process_id}/execute", response_model=WorkflowResult)
async def execute_workflow(
    process_id: UUID,
    payload: ExecuteWorkflowRequest,
    workflow: Agent4Workflow = Depends(get_agent4_workflow),
    current_user: CurrentUser = Depends(get_current_user),
) -> WorkflowResult:
    """Dispatch the authorized task to real Agent 2 at WORKFLOW_EXECUTION.

    Only valid when the process already passed the risk/approval gate
    (current stage WORKFLOW_EXECUTION). Success advances to INVOICE_MATCHING;
    failure records a BPM exception.
    """
    message_payload = {
        "task_type": payload.task_type,
        "parameters": payload.parameters,
        **payload.parameters,
    }
    try:
        return await workflow.execute_authorized(
            process_id,
            payload=message_payload,
            task_id=payload.task_id,
            correlation_id=payload.correlation_id,
        )
    except ProcessNotFoundError as exc:
        raise _not_found() from exc
    except InvalidTransitionError as exc:
        raise _invalid_transition() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc


@router.post("/{process_id}/complete-invoice-matching", response_model=WorkflowResult)
async def complete_invoice_matching(
    process_id: UUID,
    payload: InvoiceMatchingCompleteRequest,
    workflow: Agent4Workflow = Depends(get_agent4_workflow),
    current_user: CurrentUser = Depends(get_current_user),
) -> WorkflowResult:
    """INVOICE_MATCHING → COMPLETED as an explicit operator action."""
    try:
        return await workflow.complete_invoice_matching(
            process_id, reference=payload.reference
        )
    except ProcessNotFoundError as exc:
        raise _not_found() from exc
    except InvalidTransitionError as exc:
        raise _invalid_transition() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc
