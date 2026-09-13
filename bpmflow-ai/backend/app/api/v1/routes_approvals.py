"""APPROVAL endpoints backed by Agent 4 ApprovalService and ApprovalRepository."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agents.agent4_orchestrator.approval_repository import ApprovalRepository
from app.agents.agent4_orchestrator.approvals import ApprovalService
from app.agents.agent4_orchestrator.constants import (
    ApprovalStatus,
    ExceptionSeverity,
    ExceptionType,
)
from app.agents.agent4_orchestrator.exceptions import (
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    DatabasePersistenceError,
    ExecutionEnrichmentError,
)
from app.agents.agent4_orchestrator.execution_payload import (
    build_process_execution_metadata,
    require_enrich_execute_parameters,
)
from app.agents.agent4_orchestrator.repository import ProcessRepository
from app.agents.agent4_orchestrator.workflow import Agent4Workflow
from app.api.v1.deps import (
    get_agent4_workflow,
    get_approval_repository,
    get_approval_service,
    get_process_repository,
)
from app.core.security import get_current_user, require_roles
from app.schemas.approval import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalResponse,
    approval_from_record,
    decision_from_result,
)
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/approvals", tags=["approvals"])

NOT_FOUND_DETAIL = "Approval not found"
ALREADY_DECIDED_DETAIL = "Approval request has already been decided"
DATABASE_DETAIL = "Database unavailable"
INTERNAL_DETAIL = "Internal server error"
ENRICHMENT_DETAIL = "Missing discovery metadata for post-approval dispatch"


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)


def _already_decided() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=ALREADY_DECIDED_DETAIL,
    )


def _database_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=DATABASE_DETAIL,
    )


@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(
    status: ApprovalStatus | None = Query(default=None),
    repository: ApprovalRepository = Depends(get_approval_repository),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ApprovalResponse]:
    try:
        records = await repository.list_approval_requests(status=status)
    except DatabasePersistenceError as exc:
        raise _database_error() from exc
    return [approval_from_record(record) for record in records]


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: UUID,
    repository: ApprovalRepository = Depends(get_approval_repository),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApprovalResponse:
    try:
        record = await repository.get_approval_request(approval_id)
    except ApprovalNotFoundError as exc:
        raise _not_found() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc
    return approval_from_record(record)


def _execution_payload_for_approval(process, execution: dict | None) -> dict:
    """Strict enrichment — fails if discovery metadata is incomplete."""
    raw = dict(execution or {})
    parameters = raw.get("parameters") if isinstance(raw.get("parameters"), dict) else raw
    metadata_json = build_process_execution_metadata(process)
    enriched = require_enrich_execute_parameters(
        process_id=str(process.id),
        process_type=getattr(process, "process_type", None),
        process_name=getattr(process, "name", None),
        metadata_json=metadata_json,
        parameters=parameters if isinstance(parameters, dict) else {},
    )
    return {
        "task_type": raw.get("task_type") or "EXECUTE_TASK",
        "parameters": enriched,
        **enriched,
    }


@router.post("/{approval_id}/approve", response_model=ApprovalDecisionResponse)
async def approve_approval(
    approval_id: UUID,
    payload: ApprovalDecisionRequest,
    service: ApprovalService = Depends(get_approval_service),
    workflow: Agent4Workflow = Depends(get_agent4_workflow),
    repository: ProcessRepository = Depends(get_process_repository),
    current_user: CurrentUser = Depends(require_roles("approver", "admin")),
) -> ApprovalDecisionResponse:
    """Record APPROVED, then continue the workflow.

    Integration decision (explicit, user-approved): approval advances
    AWAITING_HUMAN_APPROVAL → WORKFLOW_EXECUTION via the StateMachine and
    dispatches the authorized task to Agent 2 in-process.
    """
    try:
        result = await service.approve_request(
            approval_id,
            approver_id=current_user.id,
            comments=payload.comments,
        )
        process = await repository.get_process(result.approval.process_id)
        try:
            execution_payload = _execution_payload_for_approval(process, payload.execution)
        except ExecutionEnrichmentError as exc:
            await workflow.capture_failure(
                result.approval.process_id,
                description=(
                    "Post-approval dispatch blocked: missing enrichment fields "
                    + ", ".join(exc.missing_fields)
                ),
                severity=ExceptionSeverity.HIGH,
                exception_type=ExceptionType.SYSTEM_ERROR,
                task_id=result.approval.task_id,
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": ENRICHMENT_DETAIL,
                    "missing_fields": exc.missing_fields,
                },
            ) from exc
        workflow_result = await workflow.apply_approval_outcome(
            result.approval.process_id,
            result.approval,
            execution_payload=execution_payload,
        )
    except ApprovalNotFoundError as exc:
        raise _not_found() from exc
    except ApprovalAlreadyDecidedError as exc:
        raise _already_decided() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_DETAIL,
        ) from exc
    response = decision_from_result(result)
    response.workflow = workflow_result.model_dump(mode="json")
    return response


@router.post("/{approval_id}/reject", response_model=ApprovalDecisionResponse)
async def reject_approval(
    approval_id: UUID,
    payload: ApprovalDecisionRequest,
    service: ApprovalService = Depends(get_approval_service),
    workflow: Agent4Workflow = Depends(get_agent4_workflow),
    current_user: CurrentUser = Depends(require_roles("approver", "admin")),
) -> ApprovalDecisionResponse:
    """Record REJECTED and move the process to EXCEPTION.

    Agent 2 is never invoked on rejection.
    """
    try:
        result = await service.reject_request(
            approval_id,
            approver_id=current_user.id,
            comments=payload.comments,
        )
        workflow_result = await workflow.apply_approval_outcome(
            result.approval.process_id,
            result.approval,
        )
    except ApprovalNotFoundError as exc:
        raise _not_found() from exc
    except ApprovalAlreadyDecidedError as exc:
        raise _already_decided() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_DETAIL,
        ) from exc
    response = decision_from_result(result)
    response.workflow = workflow_result.model_dump(mode="json")
    return response
