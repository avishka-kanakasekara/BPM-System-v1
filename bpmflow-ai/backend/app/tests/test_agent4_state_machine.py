"""Tests for Agent 4 BPM workflow state machine."""

from uuid import uuid4

import pytest

from app.agents.agent4_orchestrator import (
    InvalidTransitionError,
    ProcessStateTransition,
    StateMachine,
    WorkflowStage,
)


@pytest.fixture
def state_machine() -> StateMachine:
    return StateMachine()


class TestValidTransitions:
    @pytest.mark.parametrize(
        "current_stage, next_stage",
        [
            (WorkflowStage.DRAFT, WorkflowStage.DISCOVERING),
            (WorkflowStage.DISCOVERING, WorkflowStage.RESOURCE_PLANNING),
            (WorkflowStage.RESOURCE_PLANNING, WorkflowStage.RISK_REVIEW),
            (WorkflowStage.RISK_REVIEW, WorkflowStage.AWAITING_HUMAN_APPROVAL),
            (WorkflowStage.AWAITING_HUMAN_APPROVAL, WorkflowStage.WORKFLOW_EXECUTION),
            (WorkflowStage.WORKFLOW_EXECUTION, WorkflowStage.INVOICE_MATCHING),
            (WorkflowStage.INVOICE_MATCHING, WorkflowStage.COMPLETED),
            (WorkflowStage.EXCEPTION, WorkflowStage.DISCOVERING),
        ],
    )
    def test_allowed_happy_path_transitions(
        self,
        state_machine: StateMachine,
        current_stage: WorkflowStage,
        next_stage: WorkflowStage,
    ) -> None:
        assert state_machine.can_transition(current_stage, next_stage) is True
        assert state_machine.transition(current_stage, next_stage) is next_stage


class TestInvalidTransitions:
    @pytest.mark.parametrize(
        "current_stage, next_stage",
        [
            (WorkflowStage.DRAFT, WorkflowStage.COMPLETED),
            (WorkflowStage.DRAFT, WorkflowStage.WORKFLOW_EXECUTION),
            (WorkflowStage.DISCOVERING, WorkflowStage.COMPLETED),
            (WorkflowStage.COMPLETED, WorkflowStage.DRAFT),
            (WorkflowStage.AWAITING_HUMAN_APPROVAL, WorkflowStage.INVOICE_MATCHING),
        ],
    )
    def test_disallowed_transitions_raise(
        self,
        state_machine: StateMachine,
        current_stage: WorkflowStage,
        next_stage: WorkflowStage,
    ) -> None:
        assert state_machine.can_transition(current_stage, next_stage) is False
        with pytest.raises(InvalidTransitionError) as exc_info:
            state_machine.transition(current_stage, next_stage)
        assert exc_info.value.current_stage is current_stage
        assert exc_info.value.next_stage is next_stage


class TestAllowedNextStages:
    def test_draft_allows_only_discovering(self, state_machine: StateMachine) -> None:
        assert state_machine.get_allowed_next_stages(WorkflowStage.DRAFT) == [
            WorkflowStage.DISCOVERING
        ]

    def test_risk_review_allows_approval_or_execution(
        self, state_machine: StateMachine
    ) -> None:
        allowed = set(state_machine.get_allowed_next_stages(WorkflowStage.RISK_REVIEW))
        assert allowed == {
            WorkflowStage.AWAITING_HUMAN_APPROVAL,
            WorkflowStage.WORKFLOW_EXECUTION,
        }

    def test_completed_has_no_next_stages(self, state_machine: StateMachine) -> None:
        assert state_machine.get_allowed_next_stages(WorkflowStage.COMPLETED) == []

    def test_exception_allows_rediscovery_or_completion(
        self, state_machine: StateMachine
    ) -> None:
        allowed = set(state_machine.get_allowed_next_stages(WorkflowStage.EXCEPTION))
        assert allowed == {
            WorkflowStage.DISCOVERING,
            WorkflowStage.COMPLETED,
        }


class TestProcessStateTransitionSchema:
    def test_transition_model_uses_workflow_stage_enum(self) -> None:
        model = ProcessStateTransition(
            process_id=uuid4(),
            from_stage=WorkflowStage.DRAFT,
            to_stage=WorkflowStage.DISCOVERING,
            reason="Start process discovery",
        )
        assert model.from_stage is WorkflowStage.DRAFT
        assert model.to_stage is WorkflowStage.DISCOVERING
