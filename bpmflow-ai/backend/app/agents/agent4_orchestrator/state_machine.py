"""Deterministic BPM workflow state machine for Agent 4.

Explicit transition table: from-stage → to-stage → preconditions → side effects.
No LLM involvement.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum

from .constants import ApprovalStatus, WorkflowStage


class TransitionPreconditionError(ValueError):
    """Raised when a transition is allowed by stage but preconditions fail."""

    def __init__(
        self,
        current_stage: WorkflowStage,
        next_stage: WorkflowStage,
        detail: str,
    ) -> None:
        self.current_stage = current_stage
        self.next_stage = next_stage
        self.detail = detail
        super().__init__(
            f"Transition {current_stage.value} → {next_stage.value} blocked: {detail}"
        )


class InvalidTransitionError(ValueError):
    """Raised when a BPM workflow transition is not in the transition table."""

    def __init__(self, current_stage: WorkflowStage, next_stage: WorkflowStage) -> None:
        self.current_stage = current_stage
        self.next_stage = next_stage
        super().__init__(
            f"Invalid workflow transition: {current_stage.value} → {next_stage.value}"
        )


class SideEffect(str, Enum):
    """Named side effects recorded for audit / orchestration hooks."""

    START_DISCOVERY = "START_DISCOVERY"
    OPEN_RESOURCE_PLANNING = "OPEN_RESOURCE_PLANNING"
    OPEN_RISK_REVIEW = "OPEN_RISK_REVIEW"
    OPEN_HUMAN_APPROVAL_GATE = "OPEN_HUMAN_APPROVAL_GATE"
    AUTHORIZE_EXECUTION = "AUTHORIZE_EXECUTION"
    DISPATCH_AGENT2 = "DISPATCH_AGENT2"
    OPEN_INVOICE_MATCHING = "OPEN_INVOICE_MATCHING"
    COMPLETE_PROCESS = "COMPLETE_PROCESS"
    RECORD_EXCEPTION = "RECORD_EXCEPTION"
    RETRY_FROM_DISCOVERY = "RETRY_FROM_DISCOVERY"
    CLOSE_EXCEPTION = "CLOSE_EXCEPTION"


@dataclass
class TransitionContext:
    """Runtime facts required for guarded transitions."""

    human_approval_required: bool | None = None
    approval_status: ApprovalStatus | None = None
    execution_receipt_status: str | None = None
    invoice_match_status: str | None = None
    recovery_authorized: bool = False
    exception_resolved: bool = False


PreconditionFn = Callable[[TransitionContext], str | None]


def _require_human_approval(ctx: TransitionContext) -> str | None:
    if ctx.human_approval_required is False:
        return "human approval is not required for this process"
    return None


def _require_no_human_approval(ctx: TransitionContext) -> str | None:
    if ctx.human_approval_required is True:
        return "human approval is required before execution"
    return None


def _require_approval_granted(ctx: TransitionContext) -> str | None:
    if ctx.approval_status is not ApprovalStatus.APPROVED:
        return "approval must be APPROVED"
    return None


def _require_approval_rejected(ctx: TransitionContext) -> str | None:
    if ctx.approval_status is not ApprovalStatus.REJECTED:
        return "approval must be REJECTED"
    return None


def _require_execution_success(ctx: TransitionContext) -> str | None:
    if (ctx.execution_receipt_status or "").upper() != "SUCCESS":
        return "Agent 2 execution receipt must be SUCCESS"
    return None


def _require_invoice_matched(ctx: TransitionContext) -> str | None:
    if (ctx.invoice_match_status or "").upper() != "MATCHED":
        return "invoice three-way match must be MATCHED"
    return None


def _require_recovery(ctx: TransitionContext) -> str | None:
    if not ctx.recovery_authorized:
        return "exception recovery must be authorized"
    return None


def _require_exception_resolved(ctx: TransitionContext) -> str | None:
    if not ctx.exception_resolved:
        return "exception must be resolved before completion"
    return None


@dataclass(frozen=True)
class TransitionSpec:
    from_stage: WorkflowStage
    to_stage: WorkflowStage
    preconditions: tuple[PreconditionFn, ...] = ()
    side_effects: tuple[SideEffect, ...] = ()


TRANSITION_TABLE: tuple[TransitionSpec, ...] = (
    TransitionSpec(
        WorkflowStage.DRAFT,
        WorkflowStage.DISCOVERING,
        side_effects=(SideEffect.START_DISCOVERY,),
    ),
    TransitionSpec(
        WorkflowStage.DISCOVERING,
        WorkflowStage.RESOURCE_PLANNING,
        side_effects=(SideEffect.OPEN_RESOURCE_PLANNING,),
    ),
    TransitionSpec(
        WorkflowStage.RESOURCE_PLANNING,
        WorkflowStage.RISK_REVIEW,
        side_effects=(SideEffect.OPEN_RISK_REVIEW,),
    ),
    TransitionSpec(
        WorkflowStage.RISK_REVIEW,
        WorkflowStage.AWAITING_HUMAN_APPROVAL,
        preconditions=(_require_human_approval,),
        side_effects=(SideEffect.OPEN_HUMAN_APPROVAL_GATE,),
    ),
    TransitionSpec(
        WorkflowStage.RISK_REVIEW,
        WorkflowStage.WORKFLOW_EXECUTION,
        preconditions=(_require_no_human_approval,),
        side_effects=(SideEffect.AUTHORIZE_EXECUTION, SideEffect.DISPATCH_AGENT2),
    ),
    TransitionSpec(
        WorkflowStage.AWAITING_HUMAN_APPROVAL,
        WorkflowStage.WORKFLOW_EXECUTION,
        preconditions=(_require_approval_granted,),
        side_effects=(SideEffect.AUTHORIZE_EXECUTION, SideEffect.DISPATCH_AGENT2),
    ),
    TransitionSpec(
        WorkflowStage.AWAITING_HUMAN_APPROVAL,
        WorkflowStage.EXCEPTION,
        preconditions=(_require_approval_rejected,),
        side_effects=(SideEffect.RECORD_EXCEPTION,),
    ),
    TransitionSpec(
        WorkflowStage.WORKFLOW_EXECUTION,
        WorkflowStage.INVOICE_MATCHING,
        preconditions=(_require_execution_success,),
        side_effects=(SideEffect.OPEN_INVOICE_MATCHING,),
    ),
    TransitionSpec(
        WorkflowStage.WORKFLOW_EXECUTION,
        WorkflowStage.EXCEPTION,
        side_effects=(SideEffect.RECORD_EXCEPTION,),
    ),
    TransitionSpec(
        WorkflowStage.INVOICE_MATCHING,
        WorkflowStage.COMPLETED,
        preconditions=(_require_invoice_matched,),
        side_effects=(SideEffect.COMPLETE_PROCESS,),
    ),
    TransitionSpec(
        WorkflowStage.INVOICE_MATCHING,
        WorkflowStage.EXCEPTION,
        side_effects=(SideEffect.RECORD_EXCEPTION,),
    ),
    TransitionSpec(
        WorkflowStage.EXCEPTION,
        WorkflowStage.DISCOVERING,
        preconditions=(_require_recovery,),
        side_effects=(SideEffect.RETRY_FROM_DISCOVERY,),
    ),
    TransitionSpec(
        WorkflowStage.EXCEPTION,
        WorkflowStage.COMPLETED,
        preconditions=(_require_exception_resolved,),
        side_effects=(SideEffect.CLOSE_EXCEPTION, SideEffect.COMPLETE_PROCESS),
    ),
)

_TRANSITION_INDEX: dict[tuple[WorkflowStage, WorkflowStage], TransitionSpec] = {
    (spec.from_stage, spec.to_stage): spec for spec in TRANSITION_TABLE
}

ALLOWED_TRANSITIONS: dict[WorkflowStage, frozenset[WorkflowStage]] = {}
for spec in TRANSITION_TABLE:
    ALLOWED_TRANSITIONS.setdefault(spec.from_stage, frozenset())
    ALLOWED_TRANSITIONS[spec.from_stage] = frozenset(
        ALLOWED_TRANSITIONS[spec.from_stage] | {spec.to_stage}
    )


@dataclass
class TransitionResult:
    from_stage: WorkflowStage
    to_stage: WorkflowStage
    side_effects: list[SideEffect] = field(default_factory=list)


class StateMachine:
    """Deterministic BPM stage transitions. No LLM involvement."""

    def can_transition(
        self,
        current_stage: WorkflowStage,
        next_stage: WorkflowStage,
    ) -> bool:
        return next_stage in ALLOWED_TRANSITIONS.get(current_stage, frozenset())

    def get_spec(
        self,
        current_stage: WorkflowStage,
        next_stage: WorkflowStage,
    ) -> TransitionSpec | None:
        return _TRANSITION_INDEX.get((current_stage, next_stage))

    def validate_preconditions(
        self,
        current_stage: WorkflowStage,
        next_stage: WorkflowStage,
        context: TransitionContext | None,
    ) -> None:
        spec = self.get_spec(current_stage, next_stage)
        if spec is None:
            raise InvalidTransitionError(current_stage, next_stage)
        if context is None or not spec.preconditions:
            return
        for check in spec.preconditions:
            detail = check(context)
            if detail:
                raise TransitionPreconditionError(current_stage, next_stage, detail)

    def transition(
        self,
        current_stage: WorkflowStage,
        next_stage: WorkflowStage,
        context: TransitionContext | None = None,
    ) -> TransitionResult:
        if not self.can_transition(current_stage, next_stage):
            raise InvalidTransitionError(current_stage, next_stage)
        self.validate_preconditions(current_stage, next_stage, context)
        spec = self.get_spec(current_stage, next_stage)
        assert spec is not None
        return TransitionResult(
            from_stage=current_stage,
            to_stage=next_stage,
            side_effects=list(spec.side_effects),
        )

    def get_allowed_next_stages(self, current_stage: WorkflowStage) -> list[WorkflowStage]:
        return list(ALLOWED_TRANSITIONS.get(current_stage, frozenset()))

    def iter_specs(self) -> Iterable[TransitionSpec]:
        return TRANSITION_TABLE
