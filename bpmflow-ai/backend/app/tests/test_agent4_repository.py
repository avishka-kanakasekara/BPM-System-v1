"""Tests for Agent 4 process repository and database-backed orchestration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.agents.agent4_orchestrator import (
    AUDIT_ACTION_UPDATED,
    AUDIT_ENTITY_PROCESS,
    DatabasePersistenceError,
    InvalidTransitionError,
    OrchestratorService,
    ProcessNotFoundError,
    ProcessStateTransition,
    SqlAlchemyProcessRepository,
    WorkflowStage,
)
from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository
from app.models.audit import AuditLog
from app.models.process import Process

pytestmark = pytest.mark.asyncio


@pytest.fixture
def process_id():
    return uuid4()


class TestInMemoryRepository:
    async def test_read_and_update_process_stage(self, process_id) -> None:
        repo = InMemoryProcessRepository()
        await repo.create_process(process_id)

        assert await repo.get_process_stage(process_id) is WorkflowStage.DRAFT

        await repo.update_process_stage(process_id, WorkflowStage.DISCOVERING)
        assert await repo.get_process_stage(process_id) is WorkflowStage.DISCOVERING

    async def test_record_transition_history(self, process_id) -> None:
        repo = InMemoryProcessRepository()
        await repo.create_process(process_id)
        item = await repo.record_transition(
            process_id,
            WorkflowStage.DRAFT,
            WorkflowStage.DISCOVERING,
            "Start discovery",
        )
        history = await repo.get_transition_history(process_id)
        assert history == [item]

    async def test_process_not_found(self) -> None:
        repo = InMemoryProcessRepository()
        with pytest.raises(ProcessNotFoundError):
            await repo.get_process_stage(uuid4())


class TestSqlAlchemyRepository:
    async def test_get_process_stage(self, process_id) -> None:
        session = AsyncMock()
        session.get.return_value = SimpleNamespace(current_stage="DRAFT")
        repo = SqlAlchemyProcessRepository(session)

        stage = await repo.get_process_stage(process_id)

        assert stage is WorkflowStage.DRAFT
        session.get.assert_awaited_once_with(Process, process_id)

    async def test_update_process_stage(self, process_id) -> None:
        process = SimpleNamespace(current_stage="DRAFT")
        session = AsyncMock()
        session.get.return_value = process
        repo = SqlAlchemyProcessRepository(session)

        await repo.update_process_stage(process_id, WorkflowStage.DISCOVERING)

        assert process.current_stage == WorkflowStage.DISCOVERING.value

    async def test_record_transition_writes_audit_log(self, process_id) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        repo = SqlAlchemyProcessRepository(session)

        result = await repo.record_transition(
            process_id,
            WorkflowStage.DRAFT,
            WorkflowStage.DISCOVERING,
            "Start discovery",
        )

        session.add.assert_called_once()
        audit = session.add.call_args.args[0]
        assert isinstance(audit, AuditLog)
        assert audit.entity_type == AUDIT_ENTITY_PROCESS
        assert audit.entity_id == process_id
        assert audit.action == AUDIT_ACTION_UPDATED
        assert audit.old_values == {"current_stage": "DRAFT"}
        assert audit.new_values == {
            "current_stage": "DISCOVERING",
            "reason": "Start discovery",
        }
        assert result.to_stage is WorkflowStage.DISCOVERING

    async def test_process_not_found(self, process_id) -> None:
        session = AsyncMock()
        session.get.return_value = None
        repo = SqlAlchemyProcessRepository(session)

        with pytest.raises(ProcessNotFoundError):
            await repo.get_process_stage(process_id)

    async def test_database_failure_on_get(self, process_id) -> None:
        session = AsyncMock()
        session.get.side_effect = RuntimeError("connection lost")
        repo = SqlAlchemyProcessRepository(session)

        with pytest.raises(DatabasePersistenceError):
            await repo.get_process_stage(process_id)

    async def test_database_failure_on_commit(self, process_id) -> None:
        session = AsyncMock()
        session.commit.side_effect = RuntimeError("write failed")
        repo = SqlAlchemyProcessRepository(session)

        with pytest.raises(DatabasePersistenceError):
            await repo.commit()
        session.rollback.assert_awaited()


class TestOrchestratorDatabaseFlow:
    async def test_valid_transition_persists_and_audits(self, process_id) -> None:
        repo = AsyncMock()
        repo.get_process_stage.return_value = WorkflowStage.DRAFT
        repo.record_transition.return_value = ProcessStateTransition(
            process_id=process_id,
            from_stage=WorkflowStage.DRAFT,
            to_stage=WorkflowStage.DISCOVERING,
            reason="Start discovery",
        )
        service = OrchestratorService(repository=repo)

        result = await service.move_process(
            process_id,
            WorkflowStage.DISCOVERING,
            reason="Start discovery",
        )

        repo.update_process_stage.assert_awaited_once_with(
            process_id, WorkflowStage.DISCOVERING
        )
        repo.record_transition.assert_awaited_once()
        repo.commit.assert_awaited_once()
        assert result.to_stage is WorkflowStage.DISCOVERING

    async def test_invalid_transition_does_not_update_database(self, process_id) -> None:
        repo = AsyncMock()
        repo.get_process_stage.return_value = WorkflowStage.DRAFT
        service = OrchestratorService(repository=repo)

        with pytest.raises(InvalidTransitionError):
            await service.move_process(
                process_id,
                WorkflowStage.COMPLETED,
                reason="Skip to done",
            )

        repo.update_process_stage.assert_not_awaited()
        repo.record_transition.assert_not_awaited()
        repo.commit.assert_not_awaited()

    async def test_audit_event_created_after_successful_transition(self, process_id) -> None:
        repo = InMemoryProcessRepository()
        await repo.create_process(process_id)
        service = OrchestratorService(repository=repo)

        await service.move_process(
            process_id,
            WorkflowStage.DISCOVERING,
            reason="Start discovery",
        )

        history = await repo.get_transition_history(process_id)
        assert len(history) == 1
        assert history[0].from_stage is WorkflowStage.DRAFT
        assert history[0].to_stage is WorkflowStage.DISCOVERING
        assert history[0].reason == "Start discovery"

    async def test_process_not_found_is_handled(self) -> None:
        service = OrchestratorService(repository=AsyncMock())
        service._repository.get_process_stage.side_effect = ProcessNotFoundError(uuid4())

        with pytest.raises(ProcessNotFoundError):
            await service.move_process(
                uuid4(),
                WorkflowStage.DISCOVERING,
                reason="Missing process",
            )

    async def test_database_failure_is_handled(self, process_id) -> None:
        repo = AsyncMock()
        repo.get_process_stage.return_value = WorkflowStage.DRAFT
        repo.update_process_stage.side_effect = RuntimeError("disk full")
        service = OrchestratorService(repository=repo)

        with pytest.raises(DatabasePersistenceError):
            await service.move_process(
                process_id,
                WorkflowStage.DISCOVERING,
                reason="Start discovery",
            )

        repo.rollback.assert_awaited()
        repo.commit.assert_not_awaited()
