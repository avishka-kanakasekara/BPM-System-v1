"""Agent 4 process advancement engine — autonomous stage chaining.

Given a process at stage X with satisfied preconditions, advances through
agent-owned stages until a mandatory human gate (AWAITING_HUMAN_APPROVAL),
invoice input (INVOICE_MATCHING), exception, or completion.

Human sovereignty guardrails (never violated):
- No auto-approval — AWAITING_HUMAN_APPROVAL always stops the chain.
- No auto-assignment of people — Agent 3 advisory only; no approver picked.
- No autonomous spend — Agent 2 full execution suite runs only after explicit
  human approval, using discovery-enriched parameters from approved metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.agents.agent4_orchestrator.execution_payload import (
    build_process_execution_metadata,
    require_enrich_execute_parameters,
)

from .advancement_repository import AdvancementRepository
from .advancement_schemas import (
    AdvancementResult,
    AdvancementRunRecord,
    AdvancementRunStatus,
    AutonomousAction,
)
from .constants import WorkflowStage
from .exceptions import ProcessNotFoundError
from .repository import ProcessRepository
from .schemas import RiskEvaluationContext, WorkflowResult
from .service import OrchestratorService
from .workflow import Agent4Workflow

# Documented guardrails for each autonomous action (audit + tests).
AUTONOMOUS_GUARDRAILS: dict[str, str] = {
    "START_DISCOVERY": "Moves DRAFT→DISCOVERING; does not approve or spend.",
    "REQUEST_DISCOVERY": "Calls Agent 1 read-only; skips if discovery already present.",
    "RESOURCE_PLANNING": "Agent 3 advisory allocation only; no human assigned.",
    "RISK_REVIEW": "Deterministic risk engine; may open human approval gate only.",
    "EXECUTE_WORKFLOW": "Requires prior human approval; runs full Agent 2 tool suite from discovery.",
    "INVOICE_MATCHING": "Deterministic three-way match; requires operator invoice input.",
}

HUMAN_GATE_STAGES = frozenset({WorkflowStage.AWAITING_HUMAN_APPROVAL})
INPUT_GATE_STAGES = frozenset({WorkflowStage.INVOICE_MATCHING})
TERMINAL_STAGES = frozenset({WorkflowStage.COMPLETED, WorkflowStage.EXCEPTION})


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProcessAdvancementEngine:
    """Transactional, idempotent, resumable process autopilot."""

    def __init__(
        self,
        workflow: Agent4Workflow,
        orchestrator: OrchestratorService,
        process_repository: ProcessRepository,
        advancement_repository: AdvancementRepository,
    ) -> None:
        self._workflow = workflow
        self._orchestrator = orchestrator
        self._process_repository = process_repository
        self._advancement_repository = advancement_repository

    async def advance(
        self,
        process_id: UUID,
        *,
        tenant_id: UUID,
        user_id: UUID,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
        max_steps: int = 8,
        invoice_payload: dict[str, Any] | None = None,
        resource_planning: dict[str, Any] | None = None,
    ) -> AdvancementResult:
        """Advance the process through autonomous stages until a stop gate."""
        corr = correlation_id or uuid4()
        idem = idempotency_key or f"advance-{process_id}-{corr}"

        existing = await self._advancement_repository.get_by_idempotency(process_id, idem)
        if existing and existing.status is not AdvancementRunStatus.RUNNING:
            return self._result_from_run(existing, replayed=True)

        stage = await self._orchestrator.get_current_stage(process_id)
        task_id = uuid4()
        run = existing or await self._advancement_repository.create_run(
            process_id=process_id,
            correlation_id=corr,
            idempotency_key=idem,
            from_stage=stage,
            current_stage=stage,
            tenant_id=tenant_id,
            performed_by=user_id,
            task_id=task_id,
        )

        last_step: WorkflowResult | None = None
        steps = list(run.steps)

        for _ in range(max_steps):
            stage = await self._orchestrator.get_current_stage(process_id)
            if stage in HUMAN_GATE_STAGES:
                run = await self._finalize_run(
                    run,
                    status=AdvancementRunStatus.WAITING_HUMAN,
                    current_stage=stage,
                    steps=steps,
                    last_step=last_step,
                    message="Process paused at human approval gate",
                    waiting_for="human_approval",
                )
                return self._result_from_run(run)

            if stage in INPUT_GATE_STAGES:
                if invoice_payload:
                    last_step = await self._workflow.complete_invoice_matching(
                        process_id,
                        tenant_id=tenant_id,
                        **invoice_payload,
                    )
                    action = self._log_action(
                        stage,
                        "INVOICE_MATCHING",
                        last_step.success,
                        last_step.message,
                        corr,
                    )
                    steps.append(action)
                    stage = await self._orchestrator.get_current_stage(process_id)
                    if stage is WorkflowStage.COMPLETED and last_step.success:
                        run = await self._finalize_run(
                            run,
                            status=AdvancementRunStatus.COMPLETED,
                            current_stage=stage,
                            steps=steps,
                            last_step=last_step,
                            message="Process completed after invoice match",
                        )
                        return self._result_from_run(run)
                    if not last_step.success:
                        run = await self._finalize_run(
                            run,
                            status=AdvancementRunStatus.FAILED,
                            current_stage=stage,
                            steps=steps,
                            last_step=last_step,
                            message=last_step.message,
                            error_code=last_step.error_code,
                            error_message=last_step.error_message,
                        )
                        return self._result_from_run(run)
                run = await self._finalize_run(
                    run,
                    status=AdvancementRunStatus.WAITING_INPUT,
                    current_stage=stage,
                    steps=steps,
                    last_step=last_step,
                    message="Process paused for invoice evidence submission",
                    waiting_for="invoice_input",
                )
                return self._result_from_run(run)

            if stage in TERMINAL_STAGES:
                status = (
                    AdvancementRunStatus.COMPLETED
                    if stage is WorkflowStage.COMPLETED
                    else AdvancementRunStatus.FAILED
                )
                run = await self._finalize_run(
                    run,
                    status=status,
                    current_stage=stage,
                    steps=steps,
                    last_step=last_step,
                    message=f"Process at terminal stage {stage.value}",
                )
                return self._result_from_run(run)

            last_step, action = await self._execute_autonomous_step(
                process_id,
                stage=stage,
                tenant_id=tenant_id,
                user_id=user_id,
                task_id=run.task_id or task_id,
                correlation_id=corr,
                resource_planning=resource_planning,
            )
            if action:
                steps.append(action)
                run = await self._advancement_repository.update_run(
                    run.model_copy(update={"steps": steps, "current_stage": last_step.current_stage})
                )

            if not last_step.success:
                run = await self._finalize_run(
                    run,
                    status=AdvancementRunStatus.FAILED,
                    current_stage=last_step.current_stage,
                    steps=steps,
                    last_step=last_step,
                    message=last_step.message,
                    error_code=last_step.error_code,
                    error_message=last_step.error_message,
                )
                return self._result_from_run(run)

            if last_step.human_approval_required:
                run = await self._finalize_run(
                    run,
                    status=AdvancementRunStatus.WAITING_HUMAN,
                    current_stage=last_step.current_stage,
                    steps=steps,
                    last_step=last_step,
                    message="Human approval required before execution",
                    waiting_for="human_approval",
                )
                return self._result_from_run(run)

        stage = await self._orchestrator.get_current_stage(process_id)
        run = await self._finalize_run(
            run,
            status=AdvancementRunStatus.RUNNING,
            current_stage=stage,
            steps=steps,
            last_step=last_step,
            message=f"Advancement paused after {max_steps} steps; call advance again to continue",
        )
        return self._result_from_run(run)

    async def reconcile(
        self,
        *,
        process_id: UUID | None = None,
        stale_minutes: int = 15,
        tenant_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> list[AdvancementResult]:
        """Resume stale RUNNING advancement runs after a crash."""
        cutoff = _utc_now() - timedelta(minutes=stale_minutes)
        stale = await self._advancement_repository.list_stale_running(older_than=cutoff)
        if process_id is not None:
            stale = [r for r in stale if r.process_id == process_id]
        results: list[AdvancementResult] = []
        for run in stale:
            if tenant_id is None or user_id is None:
                continue
            result = await self.advance(
                run.process_id,
                tenant_id=tenant_id,
                user_id=user_id,
                correlation_id=run.correlation_id,
                idempotency_key=f"{run.idempotency_key}-resume",
            )
            results.append(result)
        return results

    async def _execute_autonomous_step(
        self,
        process_id: UUID,
        *,
        stage: WorkflowStage,
        tenant_id: UUID,
        user_id: UUID,
        task_id: UUID,
        correlation_id: UUID,
        resource_planning: dict[str, Any] | None,
    ) -> tuple[WorkflowResult, AutonomousAction | None]:
        if stage is WorkflowStage.DRAFT:
            await self._orchestrator.move_process(
                process_id,
                WorkflowStage.DISCOVERING,
                reason="Autopilot: begin discovery phase",
            )
            result = await self._maybe_request_discovery(process_id)
            action = self._log_action(
                WorkflowStage.DRAFT,
                "START_DISCOVERY",
                result.success,
                result.message,
                correlation_id,
            )
            return result, action

        if stage is WorkflowStage.DISCOVERING:
            payload = resource_planning or await self._default_resource_planning(
                process_id, user_id=user_id
            )
            result = await self._workflow.run_resource_planning(
                process_id,
                payload={
                    "human_requirements": payload["human_requirements"],
                    "budget_requirements": payload["budget_requirements"],
                },
                task_id=task_id,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
            )
            action = self._log_action(
                WorkflowStage.DISCOVERING,
                "RESOURCE_PLANNING",
                result.success,
                result.message,
                correlation_id,
            )
            return result, action

        if stage is WorkflowStage.RESOURCE_PLANNING:
            payload = resource_planning or await self._default_resource_planning(
                process_id, user_id=user_id
            )
            result = await self._workflow.run_resource_planning(
                process_id,
                payload={
                    "human_requirements": payload["human_requirements"],
                    "budget_requirements": payload["budget_requirements"],
                },
                task_id=task_id,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
            )
            action = self._log_action(
                WorkflowStage.RESOURCE_PLANNING,
                "RESOURCE_PLANNING",
                result.success,
                result.message,
                correlation_id,
            )
            return result, action

        if stage is WorkflowStage.RISK_REVIEW:
            context = await self._build_risk_context(
                process_id, user_id=user_id, tenant_id=tenant_id
            )
            result = await self._workflow.handle_risk(
                process_id,
                context,
                task_id=task_id,
                requested_by=user_id,
                tenant_id=tenant_id,
            )
            action = self._log_action(
                WorkflowStage.RISK_REVIEW,
                "RISK_REVIEW",
                result.success,
                result.message,
                correlation_id,
            )
            return result, action

        if stage is WorkflowStage.WORKFLOW_EXECUTION:
            process = await self._process_repository.get_process(process_id)
            meta = build_process_execution_metadata(process)
            enriched = require_enrich_execute_parameters(
                process_id=str(process_id),
                process_type=process.process_type,
                process_name=process.name,
                metadata_json=meta,
                parameters={},
            )
            message_payload = {
                "task_type": "EXECUTE_TASK",
                "parameters": enriched,
                **enriched,
            }
            result = await self._workflow.execute_authorized(
                process_id,
                payload=message_payload,
                task_id=task_id,
                correlation_id=correlation_id,
            )
            action = self._log_action(
                WorkflowStage.WORKFLOW_EXECUTION,
                "EXECUTE_WORKFLOW",
                result.success,
                result.message,
                correlation_id,
            )
            return result, action

        stage_after = await self._orchestrator.get_current_stage(process_id)
        return WorkflowResult(
            process_id=process_id,
            current_stage=stage_after,
            success=True,
            message=f"No autonomous action for stage {stage.value}",
        ), None

    async def _maybe_request_discovery(self, process_id: UUID) -> WorkflowResult:
        """Skip Agent 1 when discovery output is already on the process."""
        try:
            process = await self._process_repository.get_process(process_id)
        except ProcessNotFoundError:
            return await self._workflow.request_discovery(process_id)
        meta = process.metadata_json or {}
        if meta.get("process_json") or meta.get("discovery"):
            return WorkflowResult(
                process_id=process_id,
                current_stage=WorkflowStage.DISCOVERING,
                success=True,
                message="Discovery evidence already present; skipped Agent 1 request",
            )
        return await self._workflow.request_discovery(process_id)

    async def _default_resource_planning(
        self, process_id: UUID, *, user_id: UUID
    ) -> dict[str, Any]:
        """Build Agent 3 payload from discovery risk_facts on the process."""
        amount = "5000.00"
        currency = "USD"
        cost_centre = "SYN-DEP-FIN"
        try:
            process = await self._process_repository.get_process(process_id)
            meta = dict(process.metadata_json or {})
            pj = meta.get("process_json")
            if isinstance(pj, dict):
                analytics = pj.get("analytics")
                if isinstance(analytics, dict):
                    facts = analytics.get("risk_facts")
                    if isinstance(facts, dict):
                        if facts.get("purchase_amount"):
                            amount = str(facts["purchase_amount"])
                        if facts.get("currency"):
                            currency = str(facts["currency"])
                        if facts.get("cost_centre"):
                            cost_centre = str(facts["cost_centre"])
        except ProcessNotFoundError:
            pass
        deadline = (_utc_now() + timedelta(days=7)).isoformat()
        return {
            "human_requirements": {
                "resource_type": "HUMAN",
                "required_roles": ["developer"],
                "mandatory_skills": ["python"],
                "preferred_skills": ["fastapi"],
                "requester_id": str(user_id),
                "task_deadline": deadline,
                "estimated_effort_hours": "8.00",
                "process_stage": "RESOURCE_PLANNING",
            },
            "budget_requirements": {
                "resource_type": "BUDGET",
                "required_amount": amount,
                "currency": currency,
                "cost_centre": cost_centre,
                "requester_id": str(user_id),
                "task_deadline": deadline,
                "process_stage": "RESOURCE_PLANNING",
            },
        }

    async def _build_risk_context(
        self, process_id: UUID, *, user_id: UUID, tenant_id: UUID
    ) -> RiskEvaluationContext:
        from .risk_facts import merge_context_with_risk_facts, risk_facts_from_process_payload

        context = RiskEvaluationContext(requester_id=user_id)
        try:
            process = await self._process_repository.get_process(process_id)
            meta = dict(process.metadata_json or {})
            payload = meta.get("process_json")
            if not isinstance(payload, dict):
                payload = meta
            facts = risk_facts_from_process_payload(payload if isinstance(payload, dict) else {})
            updates = merge_context_with_risk_facts(
                purchase_amount=context.purchase_amount,
                currency=context.currency,
                provided_evidence=context.provided_evidence,
                confidence=context.confidence,
                facts=facts,
            )
            if updates:
                context = context.model_copy(update=updates)
        except ProcessNotFoundError:
            pass
        return await self._workflow._enrich_risk_context(  # noqa: SLF001
            process_id,
            context,
            tenant_id=tenant_id,
        )

    def _log_action(
        self,
        stage: WorkflowStage,
        action: str,
        success: bool,
        message: str,
        correlation_id: UUID,
    ) -> AutonomousAction:
        return AutonomousAction(
            stage=stage,
            action=action,
            guardrail=AUTONOMOUS_GUARDRAILS.get(action, "Autonomous orchestration step"),
            success=success,
            message=message,
            correlation_id=correlation_id,
            timestamp=_utc_now(),
        )

    async def _finalize_run(
        self,
        run: AdvancementRunRecord,
        *,
        status: AdvancementRunStatus,
        current_stage: WorkflowStage,
        steps: list[AutonomousAction],
        last_step: WorkflowResult | None,
        message: str,
        waiting_for: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> AdvancementRunRecord:
        completed_at = (
            _utc_now()
            if status
            in (
                AdvancementRunStatus.COMPLETED,
                AdvancementRunStatus.WAITING_HUMAN,
                AdvancementRunStatus.WAITING_INPUT,
                AdvancementRunStatus.FAILED,
            )
            else None
        )
        result_json = {
            "message": message,
            "waiting_for": waiting_for,
            "last_step": last_step.model_dump(mode="json") if last_step else None,
        }
        updated = run.model_copy(
            update={
                "status": status,
                "current_stage": current_stage,
                "steps": steps,
                "result_json": result_json,
                "error_code": error_code,
                "error_message": error_message,
                "completed_at": completed_at,
            }
        )
        return await self._advancement_repository.update_run(updated)

    def _result_from_run(
        self, run: AdvancementRunRecord, *, replayed: bool = False
    ) -> AdvancementResult:
        last_step = None
        waiting_for = None
        message = "Advancement run recorded"
        if run.result_json:
            waiting_for = run.result_json.get("waiting_for")
            message = str(run.result_json.get("message") or message)
            raw = run.result_json.get("last_step")
            if isinstance(raw, dict):
                last_step = WorkflowResult.model_validate(raw)
        human = run.status is AdvancementRunStatus.WAITING_HUMAN
        return AdvancementResult(
            process_id=run.process_id,
            run_id=run.id,
            correlation_id=run.correlation_id,
            idempotency_key=run.idempotency_key,
            status=run.status,
            from_stage=run.from_stage,
            current_stage=run.current_stage,
            steps_taken=len(run.steps),
            autonomous_actions=run.steps,
            waiting_for=waiting_for,
            last_step=last_step,
            message=message,
            error_code=run.error_code,
            error_message=run.error_message,
            human_approval_required=human,
            replayed=replayed,
        )
