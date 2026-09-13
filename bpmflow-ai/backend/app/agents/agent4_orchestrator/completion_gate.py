"""Deterministic procurement completion gate. Agent 4 is the only caller that may COMPLETE."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.agents.agent4_orchestrator.constants import ExceptionStatus, WorkflowStage
from app.agents.agent4_orchestrator.workflow_plan.constants import (
    WorkflowPlanStatus,
    WorkflowStepStatus,
)
from app.procurement.service import get_procurement


BLOCKING_EXCEPTION_STATUSES = frozenset({ExceptionStatus.OPEN, ExceptionStatus.IN_PROGRESS})


@dataclass
class CompletionGateResult:
    allowed: bool
    error_code: str | None = None
    reasons: list[str] = field(default_factory=list)


def evaluate_procurement_completion(
    *,
    tenant_id: UUID | None,
    process_id: UUID,
    current_stage: WorkflowStage,
    exceptions: list,
    plan=None,
    require_invoice_match: bool = True,
) -> CompletionGateResult:
    """Return whether a procurement process may move to COMPLETED.

    Amount/currency/vendor matching is not re-run here; invoice.status must already
    be MATCHED from InvoiceMatchingService.
    """
    reasons: list[str] = []
    if current_stage is WorkflowStage.COMPLETED:
        return CompletionGateResult(allowed=False, error_code="ALREADY_COMPLETED", reasons=["Process is already COMPLETED"])
    if current_stage is not WorkflowStage.INVOICE_MATCHING:
        return CompletionGateResult(
            allowed=False,
            error_code="INVALID_STAGE",
            reasons=[f"Current stage is {current_stage.value}"],
        )
    if tenant_id is None:
        return CompletionGateResult(
            allowed=False,
            error_code="INVOICE_INSUFFICIENT_EVIDENCE",
            reasons=["tenant_id is missing"],
        )

    blocking = [
        row
        for row in exceptions
        if getattr(row, "status", None) in BLOCKING_EXCEPTION_STATUSES
        and (getattr(row, "process_id", None) == process_id)
    ]
    if blocking:
        return CompletionGateResult(
            allowed=False,
            error_code="OPEN_EXCEPTION",
            reasons=["Unresolved OPEN/IN_PROGRESS exception blocks completion"],
        )

    procurement = get_procurement()
    po = procurement.get_purchase_order_for_process(tenant_id=tenant_id, process_id=process_id)
    if po is None:
        return CompletionGateResult(
            allowed=False,
            error_code="MISSING_PO",
            reasons=["No purchase order exists for this process"],
        )

    invoices = procurement.list_invoices(tenant_id=tenant_id, process_id=process_id)
    if require_invoice_match:
        if not invoices:
            return CompletionGateResult(
                allowed=False,
                error_code="MISSING_INVOICE",
                reasons=["No invoice exists for this process"],
            )
        matched = [row for row in invoices if row.status == "MATCHED"]
        if not matched:
            status = invoices[0].status
            return CompletionGateResult(
                allowed=False,
                error_code="INVOICE_NOT_MATCHED",
                reasons=[f"Invoice status is {status}, not MATCHED"],
            )
        if not (invoices[0].match_result or matched[0].match_result):
            return CompletionGateResult(
                allowed=False,
                error_code="INVOICE_NOT_MATCHED",
                reasons=["Invoice match result is missing"],
            )

    if plan is not None:
        if getattr(plan, "status", None) is not WorkflowPlanStatus.ACTIVE:
            reasons.append(f"WorkflowPlan status is {getattr(plan.status, 'value', plan.status)}")
            return CompletionGateResult(allowed=False, error_code="PLAN_NOT_ACTIVE", reasons=reasons)
        for step in plan.steps:
            if step.step_type.value == "APPROVAL" or step.step_key.endswith("-approval"):
                if step.status is not WorkflowStepStatus.COMPLETED:
                    return CompletionGateResult(
                        allowed=False,
                        error_code="PENDING_APPROVAL",
                        reasons=[f"Approval step {step.step_key} is {step.status.value}"],
                    )
            if step.required_action == "CREATE_PURCHASE_ORDER" and step.status is not WorkflowStepStatus.COMPLETED:
                return CompletionGateResult(
                    allowed=False,
                    error_code="REQUIRED_STEP_INCOMPLETE",
                    reasons=[f"Required step {step.step_key} is {step.status.value}"],
                )
            if step.status is WorkflowStepStatus.FAILED:
                return CompletionGateResult(
                    allowed=False,
                    error_code="REQUIRED_STEP_INCOMPLETE",
                    reasons=[f"Required step {step.step_key} is FAILED"],
                )

    return CompletionGateResult(allowed=True)
