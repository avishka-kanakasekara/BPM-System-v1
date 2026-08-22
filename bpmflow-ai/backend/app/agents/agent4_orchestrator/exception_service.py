"""BPM exception and recovery using public.exceptions.

Does not own StateMachine rules. Process stage changes go through OrchestratorService.
"""

from datetime import datetime, timezone
from uuid import UUID

from .constants import ExceptionSeverity, ExceptionStatus, ExceptionType, WorkflowStage
from .exception_repository import ExceptionRepository
from .exceptions import InvalidExceptionStatusError, InvalidRetryError
from .repository import AUDIT_ACTION_UPDATED
from .schemas import ExceptionRecord
from .service import OrchestratorService
from .state_machine import InvalidTransitionError


class ExceptionService:
    """Create, retry, resolve, and fail BPM exceptions."""

    def __init__(
        self,
        orchestrator: OrchestratorService,
        repository: ExceptionRepository,
    ) -> None:
        self._orchestrator = orchestrator
        self._repository = repository

    async def create_exception(
        self,
        process_id: UUID,
        description: str,
        severity: ExceptionSeverity = ExceptionSeverity.HIGH,
        exception_type: ExceptionType = ExceptionType.SYSTEM_ERROR,
        task_id: UUID | None = None,
        assigned_to: UUID | None = None,
        halt_process: bool = True,
    ) -> ExceptionRecord:
        """Insert an open exception and, when allowed, move the process to EXCEPTION."""
        record = await self._repository.create_exception(
            process_id=process_id,
            description=description,
            severity=severity,
            exception_type=exception_type,
            task_id=task_id,
            assigned_to=assigned_to,
        )
        if halt_process and await self._orchestrator.can_move(
            process_id, WorkflowStage.EXCEPTION
        ):
            await self._orchestrator.move_process(
                process_id,
                WorkflowStage.EXCEPTION,
                reason=description,
            )
        await self._repository.commit()
        return record

    async def get_exception(self, exception_id: UUID) -> ExceptionRecord:
        return await self._repository.get_exception(exception_id)

    async def resolve_exception(
        self,
        exception_id: UUID,
        resolution_notes: str,
        performed_by: UUID | None = None,
    ) -> ExceptionRecord:
        """Mark an open/in-progress exception resolved. Does not complete the process."""
        current = await self._repository.get_exception(exception_id)
        self._require_status_change(current, ExceptionStatus.RESOLVED)

        updated = current.model_copy(
            update={
                "status": ExceptionStatus.RESOLVED,
                "resolution_notes": resolution_notes,
                "resolved_at": datetime.now(timezone.utc),
            }
        )
        saved = await self._repository.update_exception(updated)
        await self._repository.record_audit(
            current.process_id,
            exception_id,
            AUDIT_ACTION_UPDATED,
            {"status": current.status.value},
            {
                "exception_id": str(exception_id),
                "status": ExceptionStatus.RESOLVED.value,
                "event": "exception_resolved",
                "resolution_notes": resolution_notes,
            },
            performed_by=performed_by,
        )
        await self._repository.commit()
        return saved

    async def retry_exception(
        self,
        exception_id: UUID,
        notes: str | None = None,
    ) -> ExceptionRecord:
        """Record one retry and, if allowed, EXCEPTION → DISCOVERING.

        The original exception row is kept. Resolved/ignored exceptions cannot retry.
        A second retry while already in_progress is rejected.
        """
        current = await self._repository.get_exception(exception_id)
        if current.status is ExceptionStatus.IN_PROGRESS:
            raise InvalidRetryError(
                f"Exception {exception_id} already has a retry in progress"
            )
        self._require_status_change(current, ExceptionStatus.IN_PROGRESS)
        if current.process_id is None:
            raise InvalidRetryError("Exception has no process_id")

        stage = await self._orchestrator.get_current_stage(current.process_id)
        if stage is not WorkflowStage.EXCEPTION:
            raise InvalidRetryError(
                f"Process is in {stage.value}, not EXCEPTION; retry is not allowed"
            )
        if not await self._orchestrator.can_move(
            current.process_id, WorkflowStage.DISCOVERING
        ):
            raise InvalidTransitionError(stage, WorkflowStage.DISCOVERING)

        retry_note = notes or "Retry requested"
        merged_notes = (
            f"{current.resolution_notes}\n{retry_note}"
            if current.resolution_notes
            else retry_note
        )
        updated = current.model_copy(
            update={
                "status": ExceptionStatus.IN_PROGRESS,
                "resolution_notes": merged_notes,
            }
        )
        saved = await self._repository.update_exception(updated)
        await self._repository.record_audit(
            current.process_id,
            exception_id,
            AUDIT_ACTION_UPDATED,
            {"status": current.status.value},
            {
                "exception_id": str(exception_id),
                "status": ExceptionStatus.IN_PROGRESS.value,
                "event": "retry_requested",
            },
        )
        await self._orchestrator.move_process(
            current.process_id,
            WorkflowStage.DISCOVERING,
            reason=f"Retry exception {exception_id}",
        )
        await self._repository.commit()
        return saved

    async def fail_exception(
        self,
        exception_id: UUID,
        notes: str | None = None,
    ) -> ExceptionRecord:
        """Terminal failure uses existing status ignored. Does not auto-complete the process."""
        current = await self._repository.get_exception(exception_id)
        self._require_status_change(current, ExceptionStatus.IGNORED)

        updated = current.model_copy(
            update={
                "status": ExceptionStatus.IGNORED,
                "resolution_notes": notes or current.resolution_notes,
                "resolved_at": datetime.now(timezone.utc),
            }
        )
        saved = await self._repository.update_exception(updated)
        await self._repository.record_audit(
            current.process_id,
            exception_id,
            AUDIT_ACTION_UPDATED,
            {"status": current.status.value},
            {
                "exception_id": str(exception_id),
                "status": ExceptionStatus.IGNORED.value,
                "event": "exception_failed",
            },
        )
        await self._repository.commit()
        return saved

    def _require_status_change(
        self,
        current: ExceptionRecord,
        target: ExceptionStatus,
    ) -> None:
        allowed = {
            ExceptionStatus.OPEN: {
                ExceptionStatus.IN_PROGRESS,
                ExceptionStatus.RESOLVED,
                ExceptionStatus.IGNORED,
            },
            ExceptionStatus.IN_PROGRESS: {
                ExceptionStatus.RESOLVED,
                ExceptionStatus.IGNORED,
            },
            ExceptionStatus.RESOLVED: set(),
            ExceptionStatus.IGNORED: set(),
        }
        if target not in allowed[current.status]:
            raise InvalidExceptionStatusError(
                current.id, current.status.value, target.value
            )
