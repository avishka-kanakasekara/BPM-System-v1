"""Tests for Agent 4 in-memory orchestration service."""

from uuid import uuid4

import pytest

from app.agents.agent4_orchestrator import (
    InvalidTransitionError,
    OrchestratorService,
    ProcessAlreadyExistsError,
    ProcessNotFoundError,
    WorkflowStage,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def service() -> OrchestratorService:
    return OrchestratorService()


class TestCreateAndGetStage:
    async def test_create_process_starts_at_draft(self, service: OrchestratorService) -> None:
        process_id = uuid4()
        stage = await service.create_process(process_id)
        assert stage is WorkflowStage.DRAFT
        assert await service.get_current_stage(process_id) is WorkflowStage.DRAFT

    async def test_duplicate_process_id_is_rejected(self, service: OrchestratorService) -> None:
        process_id = uuid4()
        await service.create_process(process_id)
        with pytest.raises(ProcessAlreadyExistsError):
            await service.create_process(process_id)

    async def test_unknown_process_raises(self, service: OrchestratorService) -> None:
        with pytest.raises(ProcessNotFoundError):
            await service.get_current_stage(uuid4())


class TestValidAndInvalidMoves:
    async def test_valid_transition_updates_stage(self, service: OrchestratorService) -> None:
        process_id = uuid4()
        await service.create_process(process_id)

        result = await service.move_process(
            process_id,
            WorkflowStage.DISCOVERING,
            reason="Start discovery",
        )

        assert result.process_id == process_id
        assert result.from_stage is WorkflowStage.DRAFT
        assert result.to_stage is WorkflowStage.DISCOVERING
        assert result.reason == "Start discovery"
        assert await service.get_current_stage(process_id) is WorkflowStage.DISCOVERING

    async def test_invalid_transition_is_rejected(self, service: OrchestratorService) -> None:
        process_id = uuid4()
        await service.create_process(process_id)

        assert await service.can_move(process_id, WorkflowStage.COMPLETED) is False
        with pytest.raises(InvalidTransitionError):
            await service.move_process(
                process_id,
                WorkflowStage.COMPLETED,
                reason="Skip to done",
            )
        assert await service.get_current_stage(process_id) is WorkflowStage.DRAFT
        assert await service.get_transition_history(process_id) == []


class TestAllowedNextStages:
    async def test_draft_allows_discovering(self, service: OrchestratorService) -> None:
        process_id = uuid4()
        await service.create_process(process_id)
        assert await service.get_allowed_next_stages(process_id) == [WorkflowStage.DISCOVERING]

    async def test_completed_cannot_transition_further(self, service: OrchestratorService) -> None:
        process_id = uuid4()
        await service.create_process(process_id, initial_stage=WorkflowStage.COMPLETED)

        assert await service.get_allowed_next_stages(process_id) == []
        assert await service.can_move(process_id, WorkflowStage.DRAFT) is False
        with pytest.raises(InvalidTransitionError):
            await service.move_process(
                process_id,
                WorkflowStage.DRAFT,
                reason="Reopen completed process",
            )


class TestIsolationAndHistory:
    async def test_multiple_processes_maintain_separate_states(
        self, service: OrchestratorService
    ) -> None:
        first = uuid4()
        second = uuid4()
        await service.create_process(first)
        await service.create_process(second)

        await service.move_process(first, WorkflowStage.DISCOVERING, reason="Advance first")

        assert await service.get_current_stage(first) is WorkflowStage.DISCOVERING
        assert await service.get_current_stage(second) is WorkflowStage.DRAFT

    async def test_transition_history_is_recorded(self, service: OrchestratorService) -> None:
        process_id = uuid4()
        await service.create_process(process_id)

        first = await service.move_process(
            process_id,
            WorkflowStage.DISCOVERING,
            reason="Start discovery",
        )
        second = await service.move_process(
            process_id,
            WorkflowStage.RESOURCE_PLANNING,
            reason="Allocate resources",
        )

        history = await service.get_transition_history(process_id)
        assert history == [first, second]
        assert [item.from_stage for item in history] == [
            WorkflowStage.DRAFT,
            WorkflowStage.DISCOVERING,
        ]
        assert [item.to_stage for item in history] == [
            WorkflowStage.DISCOVERING,
            WorkflowStage.RESOURCE_PLANNING,
        ]
