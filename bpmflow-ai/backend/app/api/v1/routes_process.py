"""PROCESS endpoints — full pipeline orchestration through Agent 4.

Every stage change goes through OrchestratorService/StateMachine. The routes
here only trigger workflow methods; they never write current_stage directly.
"""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.agent4_orchestrator.advancement_engine import ProcessAdvancementEngine
from app.agents.agent4_orchestrator.exceptions import (
    DatabasePersistenceError,
    ProcessNotFoundError,
)
from app.agents.agent4_orchestrator.execution_payload import enrich_execute_parameters
from app.agents.agent4_orchestrator.repository import ProcessRepository
from app.agents.agent4_orchestrator.schemas import RiskEvaluationContext, WorkflowResult
from app.agents.agent4_orchestrator.state_machine import InvalidTransitionError
from app.agents.agent4_orchestrator.workflow import Agent4Workflow
from app.api.v1.deps import (
    get_agent4_workflow,
    get_process_advancement_engine,
    get_process_repository,
)
from app.core.security import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.process import (
    AdvanceProcessRequest,
    AdvanceProcessResponse,
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


def _enrich_execute_parameters(
    process: ProcessResponse | None,
    parameters: dict | None,
) -> dict:
    """Ensure Agent 2 gets actionable tool parameters from discovery metadata."""
    from app.agents.agent4_orchestrator.execution_payload import (
        build_process_execution_metadata,
    )

    meta = build_process_execution_metadata(process) if process is not None else {}
    return enrich_execute_parameters(
        process_id=str(process.id) if process is not None else None,
        process_type=process.process_type if process is not None else None,
        process_name=process.name if process is not None else None,
        metadata_json=meta,
        parameters=parameters,
        strict=True,
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


@router.post("/{process_id}/advance", response_model=AdvanceProcessResponse)
async def advance_process(
    process_id: UUID,
    payload: AdvanceProcessRequest,
    engine: ProcessAdvancementEngine = Depends(get_process_advancement_engine),
    repository: ProcessRepository = Depends(get_process_repository),
    current_user: CurrentUser = Depends(get_current_user),
) -> AdvanceProcessResponse:
    """Autonomously advance the process through agent-owned stages.

    Chains DISCOVERING → RESOURCE_PLANNING → RISK_REVIEW → (human gate) and,
    after approval, WORKFLOW_EXECUTION → INVOICE_MATCHING. The only mandatory
    human stops are AWAITING_HUMAN_APPROVAL and invoice evidence input.
    """
    from app.core.config import settings

    tenant_id = current_user.tenant_id
    if payload.resource_planning and payload.resource_planning.tenant_id:
        if tenant_id is None:
            tenant_id = payload.resource_planning.tenant_id
        elif (
            settings.is_production
            and tenant_id != payload.resource_planning.tenant_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant context must come from the authenticated session",
            )
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context is required for process advancement",
        )

    if payload.reconcile_stale:
        await engine.reconcile(
            process_id=process_id,
            tenant_id=tenant_id,
            user_id=current_user.id,
        )

    invoice_payload = None
    if payload.invoice is not None:
        invoice_payload = payload.invoice.model_dump(exclude_none=True)

    resource_planning = None
    if payload.resource_planning is not None:
        rp = payload.resource_planning
        resource_planning = {
            "human_requirements": rp.human_requirements,
            "budget_requirements": rp.budget_requirements,
        }

    try:
        result = await engine.advance(
            process_id,
            tenant_id=tenant_id,
            user_id=current_user.id,
            correlation_id=payload.correlation_id,
            idempotency_key=payload.idempotency_key,
            max_steps=payload.max_steps,
            invoice_payload=invoice_payload,
            resource_planning=resource_planning,
        )
        process = await repository.get_process(process_id)
    except ProcessNotFoundError as exc:
        raise _not_found() from exc
    except InvalidTransitionError as exc:
        raise _invalid_transition() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc

    return AdvanceProcessResponse(
        process=process,
        advancement=result.model_dump(mode="json"),
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
    from app.core.config import settings

    tenant_id = current_user.tenant_id or payload.tenant_id
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context is required for resource planning",
        )
    if (
        settings.is_production
        and current_user.tenant_id is None
        and payload.tenant_id is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context must come from the authenticated session",
        )
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
        currency=payload.currency,
        required_evidence=payload.required_evidence,
        provided_evidence=payload.provided_evidence,
        confidence=(
            Decimal(str(payload.confidence)) if payload.confidence is not None else None
        ),
        requester_id=payload.requester_id or current_user.id,
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
            tenant_id=current_user.tenant_id,
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
    repository: ProcessRepository = Depends(get_process_repository),
    current_user: CurrentUser = Depends(get_current_user),
) -> WorkflowResult:
    """Dispatch the authorized task to real Agent 2 at WORKFLOW_EXECUTION.

    Only valid when the process already passed the risk/approval gate
    (current stage WORKFLOW_EXECUTION). Success advances to INVOICE_MATCHING;
    failure records a BPM exception.
    """
    _ = current_user
    try:
        process = await repository.get_process(process_id)
    except ProcessNotFoundError as exc:
        raise _not_found() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc

    parameters = _enrich_execute_parameters(process, payload.parameters)
    message_payload = {
        "task_type": payload.task_type,
        "parameters": parameters,
        **parameters,
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
    """Match invoice evidence then COMPLETED, or EXCEPTION on mismatch."""
    _ = current_user
    try:
        return await workflow.complete_invoice_matching(
            process_id,
            invoice_number=payload.invoice_number,
            amount=payload.amount,
            currency=payload.currency,
            vendor=payload.vendor,
            po_reference=payload.po_reference,
            expected_po_reference=payload.expected_po_reference,
            expected_amount=payload.expected_amount,
            expected_currency=payload.expected_currency,
            expected_vendor=payload.expected_vendor,
            expected_invoice_number=payload.expected_invoice_number,
            notes=payload.notes or payload.reference,
            reference=payload.reference,
        )
    except ProcessNotFoundError as exc:
        raise _not_found() from exc
    except InvalidTransitionError as exc:
        raise _invalid_transition() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc
