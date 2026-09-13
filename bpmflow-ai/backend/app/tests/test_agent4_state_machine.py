"""Exhaustive table-driven tests for Agent 4 BPM workflow state machine."""

from uuid import uuid4

import pytest

from app.agents.agent4_orchestrator import (
    InvalidTransitionError,
    ProcessStateTransition,
    StateMachine,
    WorkflowStage,
)
from app.agents.agent4_orchestrator.constants import ApprovalStatus
from app.agents.agent4_orchestrator.state_machine import (
    TRANSITION_TABLE,
    SideEffect,
    TransitionContext,
    TransitionPreconditionError,
    TransitionSpec,
)


@pytest.fixture
def state_machine() -> StateMachine:
    return StateMachine()


ALL_STAGES = list(WorkflowStage)


def _context_for(spec: TransitionSpec) -> TransitionContext | None:
    if spec.to_stage is WorkflowStage.AWAITING_HUMAN_APPROVAL:
        return TransitionContext(human_approval_required=True)
    if spec.from_stage is WorkflowStage.RISK_REVIEW and spec.to_stage is WorkflowStage.WORKFLOW_EXECUTION:
        return TransitionContext(human_approval_required=False)
    if spec.from_stage is WorkflowStage.AWAITING_HUMAN_APPROVAL:
        if spec.to_stage is WorkflowStage.WORKFLOW_EXECUTION:
            return TransitionContext(approval_status=ApprovalStatus.APPROVED)
        if spec.to_stage is WorkflowStage.EXCEPTION:
            return TransitionContext(approval_status=ApprovalStatus.REJECTED)
    if spec.from_stage is WorkflowStage.WORKFLOW_EXECUTION and spec.to_stage is WorkflowStage.INVOICE_MATCHING:
        return TransitionContext(execution_receipt_status="SUCCESS")
    if spec.from_stage is WorkflowStage.INVOICE_MATCHING and spec.to_stage is WorkflowStage.COMPLETED:
        return TransitionContext(invoice_match_status="MATCHED")
    if spec.from_stage is WorkflowStage.EXCEPTION and spec.to_stage is WorkflowStage.DISCOVERING:
        return TransitionContext(recovery_authorized=True)
    if spec.from_stage is WorkflowStage.EXCEPTION and spec.to_stage is WorkflowStage.COMPLETED:
        return TransitionContext(exception_resolved=True)
    return None


class TestTransitionTableCoverage:
    def test_table_lists_every_allowed_edge(self, state_machine: StateMachine) -> None:
        for spec in TRANSITION_TABLE:
            assert state_machine.can_transition(spec.from_stage, spec.to_stage)

    @pytest.mark.parametrize("spec", TRANSITION_TABLE)
    def test_allowed_transition_with_context(
        self, state_machine: StateMachine, spec: TransitionSpec
    ) -> None:
        ctx = _context_for(spec)
        result = state_machine.transition(spec.from_stage, spec.to_stage, ctx)
        assert result.to_stage is spec.to_stage
        assert result.side_effects == list(spec.side_effects)

    @pytest.mark.parametrize(
        "current_stage,next_stage",
        [
            (WorkflowStage.DRAFT, WorkflowStage.COMPLETED),
            (WorkflowStage.DRAFT, WorkflowStage.WORKFLOW_EXECUTION),
            (WorkflowStage.DISCOVERING, WorkflowStage.COMPLETED),
            (WorkflowStage.COMPLETED, WorkflowStage.DRAFT),
            (WorkflowStage.AWAITING_HUMAN_APPROVAL, WorkflowStage.INVOICE_MATCHING),
            (WorkflowStage.RISK_REVIEW, WorkflowStage.INVOICE_MATCHING),
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


class TestExceptionBranches:
    def test_approval_reject_requires_rejected_status(self, state_machine: StateMachine) -> None:
        with pytest.raises(TransitionPreconditionError):
            state_machine.transition(
                WorkflowStage.AWAITING_HUMAN_APPROVAL,
                WorkflowStage.EXCEPTION,
                TransitionContext(approval_status=ApprovalStatus.APPROVED),
            )

    def test_execution_success_required_for_invoice_matching(
        self, state_machine: StateMachine
    ) -> None:
        with pytest.raises(TransitionPreconditionError):
            state_machine.transition(
                WorkflowStage.WORKFLOW_EXECUTION,
                WorkflowStage.INVOICE_MATCHING,
                TransitionContext(execution_receipt_status="BLOCKED"),
            )

    def test_invoice_match_required_for_completion(self, state_machine: StateMachine) -> None:
        with pytest.raises(TransitionPreconditionError):
            state_machine.transition(
                WorkflowStage.INVOICE_MATCHING,
                WorkflowStage.COMPLETED,
                TransitionContext(invoice_match_status="MISMATCH"),
            )

    def test_exception_recovery_requires_authorization(self, state_machine: StateMachine) -> None:
        with pytest.raises(TransitionPreconditionError):
            state_machine.transition(
                WorkflowStage.EXCEPTION,
                WorkflowStage.DISCOVERING,
                TransitionContext(recovery_authorized=False),
            )

    def test_exception_to_completed_requires_resolution(self, state_machine: StateMachine) -> None:
        with pytest.raises(TransitionPreconditionError):
            state_machine.transition(
                WorkflowStage.EXCEPTION,
                WorkflowStage.COMPLETED,
                TransitionContext(exception_resolved=False),
            )


class TestRecoveryPaths:
    def test_exception_rediscovery_path(self, state_machine: StateMachine) -> None:
        result = state_machine.transition(
            WorkflowStage.EXCEPTION,
            WorkflowStage.DISCOVERING,
            TransitionContext(recovery_authorized=True),
        )
        assert SideEffect.RETRY_FROM_DISCOVERY in result.side_effects

    def test_exception_close_complete_path(self, state_machine: StateMachine) -> None:
        result = state_machine.transition(
            WorkflowStage.EXCEPTION,
            WorkflowStage.COMPLETED,
            TransitionContext(exception_resolved=True),
        )
        assert SideEffect.CLOSE_EXCEPTION in result.side_effects
        assert SideEffect.COMPLETE_PROCESS in result.side_effects


class TestAllowedNextStages:
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
