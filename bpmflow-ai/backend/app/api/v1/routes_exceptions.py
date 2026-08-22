"""EXCEPTION endpoints backed by Agent 4 ExceptionService and ExceptionRepository."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agents.agent4_orchestrator.constants import ExceptionStatus
from app.agents.agent4_orchestrator.exception_repository import ExceptionRepository
from app.agents.agent4_orchestrator.exception_service import ExceptionService
from app.agents.agent4_orchestrator.exceptions import (
    BpmExceptionNotFoundError,
    DatabasePersistenceError,
    InvalidExceptionStatusError,
    InvalidRetryError,
)
from app.agents.agent4_orchestrator.state_machine import InvalidTransitionError
from app.api.v1.deps import get_exception_repository, get_exception_service
from app.core.security import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.exception import (
    ExceptionActionResponse,
    ExceptionFailRequest,
    ExceptionResolveRequest,
    ExceptionResponse,
    ExceptionRetryRequest,
    action_from_record,
    exception_from_record,
)

router = APIRouter(prefix="/exceptions", tags=["exceptions"])

NOT_FOUND_DETAIL = "Exception not found"
INVALID_ACTION_DETAIL = "Invalid exception action"
DATABASE_DETAIL = "Database unavailable"
INTERNAL_DETAIL = "Internal server error"


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)


def _invalid_action() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=INVALID_ACTION_DETAIL,
    )


def _database_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=DATABASE_DETAIL,
    )


@router.get("", response_model=list[ExceptionResponse])
async def list_exceptions(
    status: ExceptionStatus | None = Query(default=None),
    repository: ExceptionRepository = Depends(get_exception_repository),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ExceptionResponse]:
    try:
        records = await repository.list_exceptions(status=status)
    except DatabasePersistenceError as exc:
        raise _database_error() from exc
    return [exception_from_record(record) for record in records]


@router.get("/{exception_id}", response_model=ExceptionResponse)
async def get_exception(
    exception_id: UUID,
    repository: ExceptionRepository = Depends(get_exception_repository),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExceptionResponse:
    try:
        record = await repository.get_exception(exception_id)
    except BpmExceptionNotFoundError as exc:
        raise _not_found() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc
    return exception_from_record(record)


@router.post("/{exception_id}/resolve", response_model=ExceptionActionResponse)
async def resolve_exception(
    exception_id: UUID,
    payload: ExceptionResolveRequest,
    service: ExceptionService = Depends(get_exception_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExceptionActionResponse:
    """Resolve an exception without auto-completing the process."""
    try:
        record = await service.resolve_exception(
            exception_id,
            resolution_notes=payload.resolution_notes,
            performed_by=current_user.id,
        )
    except BpmExceptionNotFoundError as exc:
        raise _not_found() from exc
    except (InvalidExceptionStatusError, InvalidRetryError, InvalidTransitionError) as exc:
        raise _invalid_action() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_DETAIL,
        ) from exc
    return action_from_record(record)


@router.post("/{exception_id}/retry", response_model=ExceptionActionResponse)
async def retry_exception(
    exception_id: UUID,
    payload: ExceptionRetryRequest,
    service: ExceptionService = Depends(get_exception_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExceptionActionResponse:
    """Retry an eligible exception via the existing recovery flow."""
    try:
        record = await service.retry_exception(
            exception_id,
            notes=payload.notes,
        )
    except BpmExceptionNotFoundError as exc:
        raise _not_found() from exc
    except (InvalidExceptionStatusError, InvalidRetryError, InvalidTransitionError) as exc:
        raise _invalid_action() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_DETAIL,
        ) from exc
    return action_from_record(record)


@router.post("/{exception_id}/fail", response_model=ExceptionActionResponse)
async def fail_exception(
    exception_id: UUID,
    payload: ExceptionFailRequest,
    service: ExceptionService = Depends(get_exception_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExceptionActionResponse:
    """Map terminal failure to ignored without auto-completing the process."""
    try:
        record = await service.fail_exception(
            exception_id,
            notes=payload.resolution_notes,
        )
    except BpmExceptionNotFoundError as exc:
        raise _not_found() from exc
    except (InvalidExceptionStatusError, InvalidRetryError, InvalidTransitionError) as exc:
        raise _invalid_action() from exc
    except DatabasePersistenceError as exc:
        raise _database_error() from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_DETAIL,
        ) from exc
    return action_from_record(record)
