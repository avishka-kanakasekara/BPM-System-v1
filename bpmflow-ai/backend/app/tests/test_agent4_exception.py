"""Tests for Agent 4 BPM exception and recovery handling."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.agent4_orchestrator import (
    Agent4Workflow,
    ApprovalService,
    BpmExceptionNotFoundError,
    DatabasePersistenceError,
    ExceptionService,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    InMemoryApprovalRepository,
    InMemoryExceptionRepository,
    InvalidExceptionStatusError,
    InvalidRetryError,
    OrchestratorService,
    WorkflowStage,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def orchestrator() -> OrchestratorService:
    return OrchestratorService()


@pytest.fixture
def exception_repo() -> InMemoryExceptionRepository:
    return InMemoryExceptionRepository()


@pytest.fixture
def exception_service(orchestrator, exception_repo) -> ExceptionService:
    return ExceptionService(orchestrator, exception_repo)


async def _process_at(orchestrator: OrchestratorService, stage: WorkflowStage):
    process_id = uuid4()
    await orchestrator.create_process(process_id, initial_stage=stage)
    return process_id


class TestCreateAndGet:
    async def test_create_and_retrieve_exception(
        self, exception_service, exception_repo, orchestrator
    ) -> None:
        process_id = await _process_at(orchestrator, WorkflowStage.WORKFLOW_EXECUTION)
        created = await exception_service.create_exception(
            process_id,
            description="Agent 2 failed",
            severity=ExceptionSeverity.HIGH,
            exception_type=ExceptionType.SYSTEM_ERROR,
        )
        loaded = await exception_service.get_exception(created.id)
        assert loaded.id == created.id
        assert loaded.process_id == process_id
        assert loaded.status is ExceptionStatus.OPEN
        assert loaded.description == "Agent 2 failed"
        assert loaded.resolved_at is None
        assert exception_repo.audit_events[0]["action"] == "created"

    async def test_unknown_exception_raises(self, exception_service) -> None:
        with pytest.raises(BpmExceptionNotFoundError):
            await exception_service.get_exception(uuid4())

    async def test_process_moves_to_exception_when_allowed(
        self, exception_service, orchestrator
    ) -> None:
        process_id = await _process_at(orchestrator, WorkflowStage.WORKFLOW_EXECUTION)
        await exception_service.create_exception(process_id, "Execution failed")
        assert await orchestrator.get_current_stage(process_id) is WorkflowStage.EXCEPTION

    async def test_does_not_move_when_transition_not_allowed(
        self, exception_service, orchestrator
    ) -> None:
        process_id = await _process_at(orchestrator, WorkflowStage.DRAFT)
        record = await exception_service.create_exception(process_id, "Draft issue")
        assert record.status is ExceptionStatus.OPEN
        assert await orchestrator.get_current_stage(process_id) is WorkflowStage.DRAFT


class TestRetry:
    async def test_retry_keeps_original_and_moves_to_discovering(
        self, exception_service, orchestrator
    ) -> None:
        process_id = await _process_at(orchestrator, WorkflowStage.WORKFLOW_EXECUTION)
        original = await exception_service.create_exception(process_id, "Need retry")
        retried = await exception_service.retry_exception(original.id, notes="Retry discovery")

        assert retried.id == original.id
        assert retried.description == original.description
        assert retried.status is ExceptionStatus.IN_PROGRESS
        assert "Retry discovery" in (retried.resolution_notes or "")
        still_there = await exception_service.get_exception(original.id)
        assert still_there.id == original.id
        assert await orchestrator.get_current_stage(process_id) is WorkflowStage.DISCOVERING

    async def test_invalid_retry_is_rejected(
        self, exception_service, orchestrator
    ) -> None:
        process_id = await _process_at(orchestrator, WorkflowStage.DRAFT)
        record = await exception_service.create_exception(
            process_id, "Cannot retry from draft"
        )
        with pytest.raises(InvalidRetryError):
            await exception_service.retry_exception(record.id)

    async def test_second_retry_is_rejected(
        self, exception_service, orchestrator
    ) -> None:
        process_id = await _process_at(orchestrator, WorkflowStage.WORKFLOW_EXECUTION)
        record = await exception_service.create_exception(process_id, "Once")
        await exception_service.retry_exception(record.id)
        with pytest.raises(InvalidRetryError):
            await exception_service.retry_exception(record.id)


class TestResolveAndFail:
    async def test_resolve_stores_notes_and_timestamp(
        self, exception_service, exception_repo, orchestrator
    ) -> None:
        process_id = await _process_at(orchestrator, WorkflowStage.INVOICE_MATCHING)
        record = await exception_service.create_exception(process_id, "Mismatch")
        resolved = await exception_service.resolve_exception(
            record.id, resolution_notes="Corrected invoice"
        )
        assert resolved.status is ExceptionStatus.RESOLVED
        assert resolved.resolution_notes == "Corrected invoice"
        assert resolved.resolved_at is not None
        assert any(
            event["new_values"].get("event") == "exception_resolved"
            for event in exception_repo.audit_events
            if event.get("new_values")
        )
        assert await orchestrator.get_current_stage(process_id) is WorkflowStage.EXCEPTION

    async def test_invalid_status_transition_rejected(
        self, exception_service, orchestrator
    ) -> None:
        process_id = await _process_at(orchestrator, WorkflowStage.WORKFLOW_EXECUTION)
        record = await exception_service.create_exception(process_id, "Done")
        await exception_service.resolve_exception(record.id, "fixed")
        with pytest.raises(InvalidExceptionStatusError):
            await exception_service.resolve_exception(record.id, "again")
        with pytest.raises(InvalidExceptionStatusError):
            await exception_service.fail_exception(record.id)

    async def test_fail_uses_ignored_status(
        self, exception_service, orchestrator
    ) -> None:
        process_id = await _process_at(orchestrator, WorkflowStage.WORKFLOW_EXECUTION)
        record = await exception_service.create_exception(process_id, "Unrecoverable")
        failed = await exception_service.fail_exception(record.id, notes="Gave up")
        assert failed.status is ExceptionStatus.IGNORED
        assert failed.resolved_at is not None


class TestDatabaseAndWorkflow:
    async def test_database_errors_are_handled(self, orchestrator) -> None:
        repo = AsyncMock()
        repo.create_exception.side_effect = DatabasePersistenceError("disk full")
        service = ExceptionService(orchestrator, repo)
        process_id = await _process_at(orchestrator, WorkflowStage.WORKFLOW_EXECUTION)
        with pytest.raises(DatabasePersistenceError):
            await service.create_exception(process_id, "fail write")

    async def test_workflow_capture_failure_moves_process(
        self, orchestrator, exception_repo
    ) -> None:
        exceptions = ExceptionService(orchestrator, exception_repo)
        workflow = Agent4Workflow(
            orchestrator=orchestrator,
            approval_service=ApprovalService(orchestrator, InMemoryApprovalRepository()),
            exception_service=exceptions,
        )
        process_id = await _process_at(orchestrator, WorkflowStage.WORKFLOW_EXECUTION)
        result = await workflow.capture_failure(process_id, "RPA timeout")
        assert result.bpm_exception is not None
        assert result.current_stage is WorkflowStage.EXCEPTION
        assert result.bpm_exception.status is ExceptionStatus.OPEN
