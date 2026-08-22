"""PROCESS endpoints supported without Agents 1–3."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.agent4_orchestrator.exceptions import (
    DatabasePersistenceError,
    ProcessNotFoundError,
)
from app.agents.agent4_orchestrator.repository import ProcessRepository
from app.agents.agent4_orchestrator.state_machine import InvalidTransitionError
from app.agents.agent4_orchestrator.workflow import Agent4Workflow
from app.api.v1.deps import get_agent4_workflow, get_process_repository
from app.core.security import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.process import ProcessCreate, ProcessResponse, ProcessStartResponse

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
    )
