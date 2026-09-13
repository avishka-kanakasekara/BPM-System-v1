"""BPM exception and recovery using public.exceptions.

Does not own StateMachine rules. Process stage changes go through OrchestratorService.
"""

from datetime import UTC, datetime
from uuid import UUID

from .constants import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    WorkflowStage,
    exception_type_from_code,
)
from .exception_repository import ExceptionRepository
from .exceptions import (
    CrossTenantExceptionError,
    InvalidExceptionStatusError,
    InvalidRetryError,
)
from .repository import AUDIT_ACTION_UPDATED
from .schemas import ExceptionRecord
from .service import OrchestratorService
from .state_machine import InvalidTransitionError, TransitionContext


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
        *,
        tenant_id: UUID | None = None,
        workflow_plan_id: UUID | None = None,
        workflow_step_id: UUID | None = None,
        exception_code: str | None = None,
        title: str | None = None,
        source_agent: str | None = None,
        source_operation: str | None = None,
        evidence_refs: list[str] | None = None,
        details: dict | None = None,
        assigned_employee_id: UUID | None = None,
    ) -> ExceptionRecord:
        """Insert an open exception and, when allowed, move the process to EXCEPTION."""
        code = exception_code or exception_type.value
        mapped_type = exception_type_from_code(code)
        details = dict(details or {})
        duplicate = await self._repository.find_open_duplicate(
            process_id=process_id,
            exception_code=code,
            workflow_step_id=workflow_step_id,
            invoice_id=str(details["invoice_id"]) if details.get("invoice_id") else None,
            execution_event_id=str(details["execution_event_id"]) if details.get("execution_event_id") else None,
        )
        if isinstance(duplicate, ExceptionRecord):
            if halt_process and await self._orchestrator.can_move(process_id, WorkflowStage.EXCEPTION):
                await self._orchestrator.move_process(
                    process_id,
                    WorkflowStage.EXCEPTION,
                    reason=description,
                )
            return duplicate
        record = await self._repository.create_exception(
            process_id=process_id,
            description=description,
            severity=severity,
            exception_type=mapped_type,
            task_id=task_id,
            assigned_to=assigned_to,
            tenant_id=tenant_id,
            workflow_plan_id=workflow_plan_id,
            workflow_step_id=workflow_step_id,
            exception_code=code,
            title=title or description[:200],
            source_agent=source_agent,
            source_operation=source_operation,
            evidence_refs=evidence_refs or [],
            details=details,
            assigned_employee_id=assigned_employee_id,
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

    async def get_exception(
        self, exception_id: UUID, *, tenant_id: UUID | None = None
    ) -> ExceptionRecord:
        record = await self._repository.get_exception(exception_id)
        self._assert_tenant(record, tenant_id)
        return record

    async def list_exceptions(
        self,
        status: ExceptionStatus | None = None,
        *,
        tenant_id: UUID | None = None,
        process_id: UUID | None = None,
    ) -> list[ExceptionRecord]:
        return await self._repository.list_exceptions(
            status=status, tenant_id=tenant_id, process_id=process_id
        )

    async def list_blocking_exceptions(self, process_id: UUID) -> list[ExceptionRecord]:
        open_rows = await self._repository.list_exceptions(
            status=ExceptionStatus.OPEN, process_id=process_id
        )
        progress = await self._repository.list_exceptions(
            status=ExceptionStatus.IN_PROGRESS, process_id=process_id
        )
        return open_rows + progress

    async def resolve_exception(
        self,
        exception_id: UUID,
        resolution_notes: str,
        performed_by: UUID | None = None,
        *,
        tenant_id: UUID | None = None,
        resolved_by_employee_id: UUID | None = None,
    ) -> ExceptionRecord:
        """Mark an open/in-progress exception resolved. Does not complete the process."""
        current = await self._repository.get_exception(exception_id)
        self._assert_tenant(current, tenant_id)
        if current.status is ExceptionStatus.RESOLVED:
            return current
        self._require_status_change(current, ExceptionStatus.RESOLVED)

        updated = current.model_copy(
            update={
                "status": ExceptionStatus.RESOLVED,
                "resolution_notes": resolution_notes,
                "resolved_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "resolved_by_employee_id": resolved_by_employee_id or performed_by,
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
                "process_remains": WorkflowStage.EXCEPTION.value,
                "revalidation_required": True,
            },
            performed_by=performed_by,
        )
        await self._repository.commit()
        return saved

    async def retry_exception(
        self,
        exception_id: UUID,
        notes: str | None = None,
        *,
        tenant_id: UUID | None = None,
    ) -> ExceptionRecord:
        """Record one retry and, if allowed, EXCEPTION → DISCOVERING.

        The original exception row is kept. Resolved/ignored exceptions cannot retry.
        A second retry while already in_progress is rejected.
        """
        current = await self._repository.get_exception(exception_id)
        self._assert_tenant(current, tenant_id)
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
                "updated_at": datetime.now(UTC),
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
            transition_context=TransitionContext(recovery_authorized=True),
        )
        await self._repository.commit()
        return saved

    async def fail_exception(
        self,
        exception_id: UUID,
        notes: str | None = None,
        *,
        tenant_id: UUID | None = None,
    ) -> ExceptionRecord:
        """Terminal failure uses existing status ignored. Does not auto-complete the process."""
        current = await self._repository.get_exception(exception_id)
        self._assert_tenant(current, tenant_id)
        self._require_status_change(current, ExceptionStatus.IGNORED)

        updated = current.model_copy(
            update={
                "status": ExceptionStatus.IGNORED,
                "resolution_notes": notes or current.resolution_notes,
                "resolved_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
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

    def _assert_tenant(self, record: ExceptionRecord, tenant_id: UUID | None) -> None:
        if tenant_id is None or record.tenant_id is None:
            return
        if record.tenant_id != tenant_id:
            raise CrossTenantExceptionError()

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
