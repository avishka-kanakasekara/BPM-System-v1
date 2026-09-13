"""Higher-level BPM orchestration coordinator for Agent 4.

Coordinates OrchestratorService, RiskAnalysisEngine, ApprovalService, and
AgentCommunicationService. Does not contain SQL, transition tables, risk
rules, or allocation logic.
"""

import asyncio
from typing import Any
from uuid import UUID, uuid4

from app.schemas.agent_message import (
    AGENT_1,
    AGENT_2,
    AGENT_3,
    AGENT_4,
    AgentMessage,
    AgentMessageMetadata,
    AgentMessageType,
)

from .approvals import ApprovalService
from .communication_service import AgentCommunicationService
from .constants import ApprovalStatus, ExceptionSeverity, ExceptionType, WorkflowStage
from .exception_service import ExceptionService
from .exceptions import (
    AgentUnavailableError,
    CommunicationFailureError,
    DatabasePersistenceError,
    InvalidMessageError,
    ProcessNotFoundError,
    UnsupportedAgentError,
)
from .message_repository import AgentMessageRepository
from .risk_rules import RiskAnalysisEngine
from .schemas import (
    ApprovalRequestRecord,
    RiskAssessment,
    RiskEvaluationContext,
    WorkflowResult,
)
from .service import OrchestratorService
from .state_machine import InvalidTransitionError, TransitionContext


def _load_invoice_match_context(process_id: UUID) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load metadata_json / process_json for invoice matching when reachable."""
    try:
        from app.core.supabase_rest import rest_select, supabase_rest_configured

        if not supabase_rest_configured():
            return {}, {}
        rows = rest_select(
            "processes",
            {
                "id": f"eq.{process_id}",
                "select": "metadata_json,process_json",
                "limit": "1",
            },
        )
        if not rows:
            return {}, {}
        row = rows[0]
        meta = row.get("metadata_json") if isinstance(row.get("metadata_json"), dict) else {}
        payload = row.get("process_json") if isinstance(row.get("process_json"), dict) else {}
        return meta, payload
    except Exception:
        return {}, {}


class Agent4Workflow:
    """Coordinates the BPM lifecycle. State changes go through OrchestratorService."""

    def __init__(
        self,
        orchestrator: OrchestratorService,
        risk_engine: RiskAnalysisEngine | None = None,
        approval_service: ApprovalService | None = None,
        communication: AgentCommunicationService | None = None,
        exception_service: ExceptionService | None = None,
        policy_retrieval: Any | None = None,
        message_repository: AgentMessageRepository | None = None,
    ) -> None:
        if approval_service is None:
            raise ValueError("ApprovalService is required for Agent4Workflow")
        self._orchestrator = orchestrator
        self._risk_engine = risk_engine or RiskAnalysisEngine()
        self._approvals = approval_service
        self._message_repository = message_repository
        self._communication = communication or AgentCommunicationService(
            message_repository=message_repository
        )
        self._exceptions = exception_service
        self._policy_retrieval = policy_retrieval

    async def capture_failure(
        self,
        process_id: UUID,
        description: str,
        severity: ExceptionSeverity | None = None,
        exception_type: ExceptionType | None = None,
        task_id: UUID | None = None,
    ) -> WorkflowResult:
        """Record a BPM exception and halt the process when the StateMachine allows it."""
        if self._exceptions is None:
            raise ValueError("ExceptionService is required for capture_failure")
        record = await self._exceptions.create_exception(
            process_id=process_id,
            description=description,
            severity=severity or ExceptionSeverity.HIGH,
            exception_type=exception_type or ExceptionType.SYSTEM_ERROR,
            task_id=task_id,
            halt_process=True,
        )
        stage = await self._orchestrator.get_current_stage(process_id)
        return WorkflowResult(
            process_id=process_id,
            current_stage=stage,
            success=True,
            message="BPM exception recorded",
            bpm_exception=record,
        )

    async def start_process(self, process_id: UUID) -> WorkflowResult:
        """Create a process at DRAFT and move it to DISCOVERING, then request Agent 1."""
        await self._orchestrator.create_process(process_id)
        await self._orchestrator.move_process(
            process_id,
            WorkflowStage.DISCOVERING,
            reason="Start process discovery",
        )
        return await self._request_discovery(process_id)

    async def start_existing_process(self, process_id: UUID) -> WorkflowResult:
        """Move an existing DRAFT process to DISCOVERING, then request Agent 1.

        Does not create a process row. Does not fake discovery success.
        """
        await self._orchestrator.move_process(
            process_id,
            WorkflowStage.DISCOVERING,
            reason="Start process discovery",
        )
        return await self._request_discovery(process_id)

    async def advance_process(
        self,
        process_id: UUID,
        next_stage: WorkflowStage,
        reason: str,
    ) -> WorkflowResult:
        """Apply an explicit, StateMachine-validated stage change."""
        try:
            await self._orchestrator.move_process(process_id, next_stage, reason)
        except InvalidTransitionError:
            raise
        stage = await self._orchestrator.get_current_stage(process_id)
        return WorkflowResult(
            process_id=process_id,
            current_stage=stage,
            success=True,
            message=f"Advanced to {stage.value}",
        )

    async def request_discovery(self, process_id: UUID) -> WorkflowResult:
        """Ask Agent 1 to discover the process. Does not fake success."""
        return await self._request_discovery(process_id)

    async def plan_resources(
        self,
        process_id: UUID,
        payload: dict | None = None,
        task_id: UUID | None = None,
        tenant_id: UUID | None = None,
        correlation_id: UUID | None = None,
    ) -> WorkflowResult:
        """Send a resource-allocation request through the Agent 3 adapter boundary."""
        return await self._send_to_agent(
            process_id=process_id,
            receiver=AGENT_3,
            message_type=AgentMessageType.RESOURCE_ALLOCATION_REQUEST,
            payload=payload or {},
            task_id=task_id,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            success_type=AgentMessageType.RESOURCE_ALLOCATION_RESPONSE,
            unavailable_message="Agent 3 resource planning is unavailable",
        )

    async def run_resource_planning(
        self,
        process_id: UUID,
        payload: dict | None = None,
        task_id: UUID | None = None,
        tenant_id: UUID | None = None,
        correlation_id: UUID | None = None,
    ) -> WorkflowResult:
        """DISCOVERING → RESOURCE_PLANNING, call real Agent 3, then → RISK_REVIEW.

        The stage only advances to RISK_REVIEW when Agent 3 returns a real
        recommendation; a failed allocation leaves the process at
        RESOURCE_PLANNING with an honest error result. Retry is allowed when
        already at RESOURCE_PLANNING (no second StateMachine hop required).
        """
        stage = await self._orchestrator.get_current_stage(process_id)
        if stage is WorkflowStage.DISCOVERING:
            await self._orchestrator.move_process(
                process_id,
                WorkflowStage.RESOURCE_PLANNING,
                reason="Begin resource planning with Agent 3",
            )
        elif stage is not WorkflowStage.RESOURCE_PLANNING:
            raise InvalidTransitionError(stage, WorkflowStage.RESOURCE_PLANNING)
        result = await self.plan_resources(
            process_id,
            payload=payload,
            task_id=task_id,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )
        if not result.success:
            return result

        # Persist the full Agent 3 allocation snapshot on the process so the
        # frontend can render ranked candidates / budget / gaps after refresh.
        if result.agent_response:
            try:
                from app.agents.agent2_execution.database.persistence import (
                    merge_process_metadata,
                )

                await merge_process_metadata(
                    None,
                    str(process_id),
                    {"agent3_allocation": result.agent_response},
                )
            except Exception:
                # Planning succeeded; metadata write must not block the stage move.
                pass

        await self._orchestrator.move_process(
            process_id,
            WorkflowStage.RISK_REVIEW,
            reason="Resource recommendation received; awaiting risk review",
        )
        stage = await self._orchestrator.get_current_stage(process_id)
        return result.model_copy(update={"current_stage": stage})

    async def handle_risk(
        self,
        process_id: UUID,
        context: RiskEvaluationContext,
        task_id: UUID | None = None,
        requested_by: UUID | None = None,
        tenant_id: UUID | None = None,
    ) -> WorkflowResult:
        """Run risk review at RISK_REVIEW with optional company-policy enrichment."""
        enriched = await self._enrich_risk_context(
            process_id, context, tenant_id=tenant_id
        )
        self._record_policy_audit(
            process_id,
            "RISK_ANALYSIS_STARTED",
            {
                "tenant_id": str(tenant_id) if tenant_id else None,
                "has_policy_snapshot": enriched.policy_snapshot is not None,
            },
        )
        if enriched.policy_snapshot is not None:
            self._record_policy_audit(
                process_id,
                "POLICY_RETRIEVED",
                {
                    "status": enriched.policy_snapshot.status.value,
                    "policy_versions": enriched.policy_snapshot.policy_versions,
                    "confidence": (
                        str(enriched.policy_snapshot.confidence)
                        if enriched.policy_snapshot.confidence is not None
                        else None
                    ),
                    "message": enriched.policy_snapshot.message,
                },
            )
            if enriched.policy_snapshot.status.value == "CONFLICT":
                self._record_policy_audit(
                    process_id,
                    "POLICY_CONFLICT",
                    {"message": enriched.policy_snapshot.message},
                )
            if enriched.policy_snapshot.status.value in (
                "NOT_FOUND",
                "INSUFFICIENT_EVIDENCE",
            ):
                self._record_policy_audit(
                    process_id,
                    "POLICY_UNCERTAINTY",
                    {"message": enriched.policy_snapshot.message},
                )

        assessment = self._risk_engine.evaluate(enriched)
        decision = self._build_policy_decision(process_id, assessment)
        if assessment.findings:
            self._record_policy_audit(
                process_id,
                "RISK_IDENTIFIED",
                {
                    "overall_risk_level": (
                        assessment.overall_risk_level.value
                        if assessment.overall_risk_level
                        else None
                    ),
                    "findings": [f.risk_type.value for f in assessment.findings],
                },
            )
        try:
            if self._approvals.requires_human_approval(assessment):
                gate = await self._approvals.apply_risk_assessment(
                    process_id,
                    assessment,
                    task_id=task_id,
                    requested_by=requested_by,
                )
                self._record_policy_audit(
                    process_id,
                    "APPROVAL_REQUIRED",
                    {
                        "approval_id": str(gate.approval.id) if gate.approval else None,
                        "risk_level": (
                            assessment.overall_risk_level.value
                            if assessment.overall_risk_level
                            else None
                        ),
                    },
                )
                stage = await self._orchestrator.get_current_stage(process_id)
                return WorkflowResult(
                    process_id=process_id,
                    current_stage=stage,
                    success=True,
                    message="Human approval required",
                    human_approval_required=True,
                    approval=gate.approval,
                    risk_assessment=assessment,
                    policy_decision=decision,
                    eligible_for_execution=False,
                )

            if any(f.recommendation.value == "BLOCK_ACTION" for f in assessment.findings):
                self._record_policy_audit(
                    process_id,
                    "EXECUTION_BLOCKED",
                    {"findings": [f.risk_type.value for f in assessment.findings]},
                )
                if self._exceptions is not None:
                    record = await self._exceptions.create_exception(
                        process_id=process_id,
                        description="Risk analysis blocked unauthorized action",
                        severity=ExceptionSeverity.CRITICAL,
                        exception_type=ExceptionType.SYSTEM_ERROR,
                        task_id=task_id,
                        halt_process=True,
                    )
                    stage = await self._orchestrator.get_current_stage(process_id)
                    return WorkflowResult(
                        process_id=process_id,
                        current_stage=stage,
                        success=False,
                        message="Execution blocked by risk controls",
                        error_code="EXECUTION_BLOCKED",
                        risk_assessment=assessment,
                        policy_decision=decision,
                        bpm_exception=record,
                        eligible_for_execution=False,
                    )
                stage = await self._orchestrator.get_current_stage(process_id)
                return WorkflowResult(
                    process_id=process_id,
                    current_stage=stage,
                    success=False,
                    message="Execution blocked by risk controls",
                    error_code="EXECUTION_BLOCKED",
                    risk_assessment=assessment,
                    policy_decision=decision,
                    eligible_for_execution=False,
                )

            await self._orchestrator.move_process(
                process_id,
                WorkflowStage.WORKFLOW_EXECUTION,
                reason="No human-approval risk findings",
                transition_context=TransitionContext(human_approval_required=False),
            )
            self._record_policy_audit(
                process_id,
                "EXECUTION_AUTHORIZED",
                {"reason": "No human-approval risk findings"},
            )
            stage = await self._orchestrator.get_current_stage(process_id)
            return WorkflowResult(
                process_id=process_id,
                current_stage=stage,
                success=True,
                message="No human approval required; process is eligible for execution",
                human_approval_required=False,
                risk_assessment=assessment,
                policy_decision=decision,
                eligible_for_execution=True,
            )
        except InvalidTransitionError:
            raise
        except (DatabasePersistenceError, ProcessNotFoundError):
            raise

    def _record_policy_audit(
        self, process_id: UUID, action: str, metadata: dict[str, Any]
    ) -> None:
        """Best-effort audit write for policy/risk events (never raises)."""
        try:
            from uuid import uuid4 as _uuid4

            from app.core.supabase_rest import rest_insert, supabase_rest_configured

            if not supabase_rest_configured():
                return
            rest_insert(
                "audit_logs",
                {
                    "id": str(_uuid4()),
                    "entity_type": "process",
                    "entity_id": str(process_id),
                    "action": action,
                    "performed_by": None,
                    "old_values": None,
                    "new_values": metadata,
                },
            )
        except Exception:
            return

    async def _enrich_risk_context(
        self,
        process_id: UUID,
        context: RiskEvaluationContext,
        *,
        tenant_id: UUID | None,
    ) -> RiskEvaluationContext:
        from decimal import Decimal

        from .risk_facts import merge_context_with_risk_facts, risk_facts_from_process_payload

        meta, process_json = await asyncio.to_thread(_load_invoice_match_context, process_id)
        facts = risk_facts_from_process_payload(process_json)
        if not facts and isinstance(meta, dict):
            nested = meta.get("process_json")
            facts = risk_facts_from_process_payload(nested if isinstance(nested, dict) else {})

        discovery_confidence = None
        if isinstance(process_json, dict):
            conf = process_json.get("confidence")
            if isinstance(conf, dict):
                values = [Decimal(str(v)) for v in conf.values() if v is not None]
                if values:
                    discovery_confidence = sum(values) / Decimal(len(values))

        # Agent 3 budget request amount can stand in when discovery has no amount.
        if facts.get("purchase_amount") is None and isinstance(meta, dict):
            allocation = meta.get("agent3_allocation")
            if isinstance(allocation, dict):
                req = allocation.get("request") or allocation.get("budget_requirements")
                if isinstance(req, dict) and req.get("required_amount") is not None:
                    facts = {
                        **facts,
                        "purchase_amount": str(req["required_amount"]),
                        "currency": facts.get("currency") or req.get("currency"),
                    }

        updates = merge_context_with_risk_facts(
            purchase_amount=context.purchase_amount,
            currency=context.currency,
            provided_evidence=context.provided_evidence,
            confidence=context.confidence,
            facts=facts,
            discovery_confidence=discovery_confidence,
        )
        enriched = context.model_copy(update=updates) if updates else context

        if enriched.policy_snapshot is not None:
            return enriched
        if tenant_id is None or self._policy_retrieval is None:
            return enriched

        available_budget = enriched.available_budget
        if available_budget is None:
            available_budget = self._load_available_budget(process_id)

        snapshot = await self._policy_retrieval.build_risk_snapshot(
            tenant_id=tenant_id,
            purchase_amount=enriched.purchase_amount,
            available_budget=available_budget,
        )
        policy_updates: dict[str, Any] = {"policy_snapshot": snapshot}
        if available_budget is not None and enriched.available_budget is None:
            policy_updates["available_budget"] = available_budget
        if snapshot.currency and not enriched.currency:
            policy_updates["currency"] = snapshot.currency
        return enriched.model_copy(update=policy_updates)

    def _load_available_budget(self, process_id: UUID):
        try:
            from decimal import Decimal

            from app.core.supabase_rest import rest_select, supabase_rest_configured

            if not supabase_rest_configured():
                return None
            rows = rest_select(
                "processes",
                {"id": f"eq.{process_id}", "select": "metadata_json", "limit": "1"},
            )
            if not rows:
                return None
            meta = rows[0].get("metadata_json") if isinstance(rows[0], dict) else None
            if not isinstance(meta, dict):
                return None
            allocation = meta.get("agent3_allocation")
            if not isinstance(allocation, dict):
                return None
            recommendation = allocation.get("recommendation")
            if not isinstance(recommendation, dict):
                return None
            budget_result = recommendation.get("budget_requirement_result")
            if not isinstance(budget_result, dict):
                return None
            validation = budget_result.get("budget_validation")
            if not isinstance(validation, dict):
                return None
            raw = validation.get("available_balance")
            if raw is None:
                return None
            return Decimal(str(raw))
        except Exception:
            return None

    def _build_policy_decision(self, process_id: UUID, assessment: RiskAssessment):
        from app.policy_knowledge.schemas import PolicyDecisionPackage

        snapshot = assessment.policy_snapshot
        findings = [
            {
                "category": f.risk_type.value,
                "reason": f.description,
                "amount": str(f.amount) if f.amount is not None else None,
                "threshold": str(f.threshold) if f.threshold is not None else None,
                "currency": f.currency,
                "evidence_refs": f.evidence_refs,
                "policy_version": f.policy_version,
                "recommendation": f.recommendation.value,
            }
            for f in assessment.findings
        ]
        approval_required = self._approvals.requires_human_approval(assessment)
        blocking = approval_required or any(
            f.recommendation.value == "BLOCK_ACTION" for f in assessment.findings
        )
        return PolicyDecisionPackage(
            process_id=process_id,
            risk_level=(
                assessment.overall_risk_level.value
                if assessment.overall_risk_level
                else None
            ),
            risk_findings=findings,
            policy_evidence=list(snapshot.evidence) if snapshot else [],
            evidence_refs=[ref for f in assessment.findings for ref in f.evidence_refs],
            controls_required=sorted({f.recommendation.value for f in assessment.findings}),
            approval_required=approval_required,
            blocking=blocking,
            confidence=snapshot.confidence if snapshot else None,
            policy_version=(
                snapshot.policy_versions[0]
                if snapshot and snapshot.policy_versions
                else None
            ),
            policy_retrieval_status=snapshot.status if snapshot else None,
        )

    async def request_human_approval(
        self,
        process_id: UUID,
        assessment: RiskAssessment,
        task_id: UUID | None = None,
        requested_by: UUID | None = None,
    ) -> WorkflowResult:
        """Create a PENDING approval via ApprovalService."""
        gate = await self._approvals.apply_risk_assessment(
            process_id,
            assessment,
            task_id=task_id,
            requested_by=requested_by,
        )
        stage = await self._orchestrator.get_current_stage(process_id)
        return WorkflowResult(
            process_id=process_id,
            current_stage=stage,
            success=True,
            message="Human approval requested" if gate.human_approval_required else "Approval not required",
            human_approval_required=gate.human_approval_required,
            approval=gate.approval,
            risk_assessment=assessment,
        )

    async def apply_approval_outcome(
        self,
        process_id: UUID,
        approval: ApprovalRequestRecord,
        execution_payload: dict | None = None,
        correlation_id: UUID | None = None,
    ) -> WorkflowResult:
        """Interpret PENDING / APPROVED / REJECTED.

        Integration decision (explicit, user-approved): APPROVED advances
        AWAITING_HUMAN_APPROVAL → WORKFLOW_EXECUTION via the StateMachine and
        dispatches the authorized task to Agent 2 in-process. REJECTED moves
        the process to EXCEPTION and never reaches Agent 2.
        """
        stage = await self._orchestrator.get_current_stage(process_id)
        if approval.status is ApprovalStatus.PENDING:
            return WorkflowResult(
                process_id=process_id,
                current_stage=stage,
                success=True,
                message="Approval is pending; execution will not continue",
                human_approval_required=True,
                approval=approval,
                eligible_for_execution=False,
            )
        if approval.status is ApprovalStatus.APPROVED:
            await self._orchestrator.move_process(
                process_id,
                WorkflowStage.WORKFLOW_EXECUTION,
                reason="Human approval granted",
                transition_context=TransitionContext(
                    approval_status=ApprovalStatus.APPROVED
                ),
            )
            result = await self.execute_authorized(
                process_id,
                payload=execution_payload,
                task_id=approval.task_id,
                correlation_id=correlation_id,
            )
            return result.model_copy(
                update={"approval": approval, "eligible_for_execution": True}
            )
        if approval.status is ApprovalStatus.REJECTED:
            await self._orchestrator.move_process(
                process_id,
                WorkflowStage.EXCEPTION,
                reason="Human approval rejected",
                transition_context=TransitionContext(
                    approval_status=ApprovalStatus.REJECTED
                ),
            )
            stage = await self._orchestrator.get_current_stage(process_id)
            return WorkflowResult(
                process_id=process_id,
                current_stage=stage,
                success=True,
                message="Approval rejected; process moved to EXCEPTION",
                approval=approval,
                eligible_for_execution=False,
            )
        return WorkflowResult(
            process_id=process_id,
            current_stage=stage,
            success=False,
            message=f"Unhandled approval status {approval.status.value}",
            error_code="UNHANDLED_APPROVAL_STATUS",
            approval=approval,
        )

    async def execute_workflow(
        self,
        process_id: UUID,
        payload: dict | None = None,
        task_id: UUID | None = None,
        correlation_id: UUID | None = None,
    ) -> WorkflowResult:
        """Request Agent 2 execution. Does not fake success if Agent 2 is unavailable.

        The message carries status="AUTHORIZED" — Agent 4 is the only agent
        allowed to mark work as authorized, and it only calls this after the
        risk/approval gate.
        """
        return await self._send_to_agent(
            process_id=process_id,
            receiver=AGENT_2,
            message_type=AgentMessageType.WORKFLOW_EXECUTION_REQUEST,
            payload=payload or {},
            task_id=task_id,
            correlation_id=correlation_id,
            success_type=AgentMessageType.WORKFLOW_EXECUTION_RESPONSE,
            unavailable_message="Agent 2 workflow execution is unavailable",
            message_status="AUTHORIZED",
        )

    async def execute_authorized(
        self,
        process_id: UUID,
        payload: dict | None = None,
        task_id: UUID | None = None,
        correlation_id: UUID | None = None,
    ) -> WorkflowResult:
        """Run Agent 2 at WORKFLOW_EXECUTION and advance or record an exception.

        On a successful execution receipt the process moves
        WORKFLOW_EXECUTION → INVOICE_MATCHING. On a blocked/policy failure a BPM
        exception is recorded. Transient Agent 2 / LLM outages leave the process
        at WORKFLOW_EXECUTION so human approval is not discarded — callers can retry.
        """
        stage = await self._orchestrator.get_current_stage(process_id)
        if stage is not WorkflowStage.WORKFLOW_EXECUTION:
            return WorkflowResult(
                process_id=process_id,
                current_stage=stage,
                success=False,
                message="Process is not at WORKFLOW_EXECUTION",
                error_code="INVALID_STAGE",
                error_message=f"Current stage is {stage.value}",
            )

        result = await self.execute_workflow(
            process_id,
            payload=payload,
            task_id=task_id,
            correlation_id=correlation_id,
        )

        receipt_status = ""
        if result.agent_response:
            receipt_status = str(result.agent_response.get("receipt_status") or "")

        if result.success and receipt_status == "SUCCESS":
            await self._orchestrator.move_process(
                process_id,
                WorkflowStage.INVOICE_MATCHING,
                reason="Agent 2 execution succeeded",
                transition_context=TransitionContext(
                    execution_receipt_status="SUCCESS"
                ),
            )
            stage = await self._orchestrator.get_current_stage(process_id)
            return result.model_copy(update={"current_stage": stage})

        failure_detail = (
            result.error_message
            or (result.agent_response or {}).get("error_message")
            or (result.agent_response or {}).get("detail")
            or f"Agent 2 execution did not succeed (receipt_status={receipt_status or 'UNKNOWN'})"
        )

        # Policy / authorization blocks still halt.
        if receipt_status == "BLOCKED":
            if self._exceptions is not None:
                return await self.capture_failure(
                    process_id,
                    description=str(failure_detail),
                    severity=ExceptionSeverity.HIGH,
                    exception_type=ExceptionType.SYSTEM_ERROR,
                    task_id=task_id,
                )
            return result.model_copy(update={"success": False})

        # Transient LLM/infra failures must not undo human approval.
        if self._is_retryable_agent2_failure(result, failure_detail=str(failure_detail)):
            stage = await self._orchestrator.get_current_stage(process_id)
            return result.model_copy(
                update={
                    "success": False,
                    "current_stage": stage,
                    "message": (
                        "Human authorization remains valid, but Agent 2 execution "
                        "could not complete (temporary LLM/service issue). "
                        "Retry Execute from the process page."
                    ),
                    "error_code": "AGENT2_RETRYABLE_FAILURE",
                    "error_message": str(failure_detail),
                    "eligible_for_execution": True,
                }
            )

        if self._exceptions is not None:
            return await self.capture_failure(
                process_id,
                description=str(failure_detail),
                severity=ExceptionSeverity.HIGH,
                exception_type=ExceptionType.SYSTEM_ERROR,
                task_id=task_id,
            )
        return result.model_copy(update={"success": False})

    @staticmethod
    def _is_retryable_agent2_failure(
        result: WorkflowResult,
        *,
        failure_detail: str,
    ) -> bool:
        """True for transient LLM/quota/network failures that should not halt the process."""
        if result.error_code in {"AGENT_UNAVAILABLE", "COMMUNICATION_FAILURE"}:
            return True
        payload = result.agent_response or {}
        if payload.get("error") in {"AGENT2_EXECUTION_FAILED"}:
            return True
        blob = " ".join(
            str(part)
            for part in (
                failure_detail,
                result.error_message,
                result.message,
                payload.get("detail"),
                payload.get("error_message"),
                payload.get("error"),
            )
            if part
        ).lower()
        markers = (
            "resource_exhausted",
            "429",
            "quota",
            "unavailable",
            "real llm execution is required",
            "gemini",
            "timeout",
            "connection",
            "ssl",
            "certificate",
        )
        return any(marker in blob for marker in markers)

    async def complete_invoice_matching(
        self,
        process_id: UUID,
        *,
        invoice_number: str | None = None,
        amount: float | None = None,
        currency: str | None = None,
        vendor: str | None = None,
        po_reference: str | None = None,
        expected_po_reference: str | None = None,
        expected_amount: float | None = None,
        expected_currency: str | None = None,
        expected_vendor: str | None = None,
        expected_invoice_number: str | None = None,
        notes: str = "",
        reference: str = "",
        tenant_id: UUID | None = None,
    ) -> WorkflowResult:
        """Match invoice evidence, then COMPLETED or EXCEPTION.

        Never advances to COMPLETED without a deterministic MATCHED result.
        """
        from decimal import Decimal

        from .invoice_matching import (
            INSUFFICIENT_EVIDENCE,
            MISMATCH,
            InvoiceEvidence,
            extract_expected_from_process,
            extract_receipt_from_process,
            merge_expected,
            three_way_match,
            tolerance_from_policy_rules,
        )

        stage = await self._orchestrator.get_current_stage(process_id)
        if stage is not WorkflowStage.INVOICE_MATCHING:
            return WorkflowResult(
                process_id=process_id,
                current_stage=stage,
                success=False,
                message="Process is not at INVOICE_MATCHING",
                error_code="INVALID_STAGE",
                error_message=f"Current stage is {stage.value}",
            )

        metadata, process_json = await asyncio.to_thread(
            _load_invoice_match_context, process_id
        )

        invoice = InvoiceEvidence(
            invoice_number=invoice_number,
            amount=Decimal(str(amount)) if amount is not None else None,
            currency=currency,
            vendor=vendor,
            po_reference=po_reference,
            notes=notes or reference or "",
        )
        expected = merge_expected(
            extract_expected_from_process(
                metadata=metadata,
                process_json=process_json,
            ),
            expected_po_reference=expected_po_reference,
            expected_amount=expected_amount,
            expected_currency=expected_currency,
            expected_vendor=expected_vendor,
            expected_invoice_number=expected_invoice_number,
        )
        receipt = extract_receipt_from_process(
            metadata=metadata,
            process_json=process_json,
        )
        if receipt.amount is None and expected.amount is not None:
            receipt.amount = expected.amount
        if receipt.po_reference is None:
            receipt.po_reference = expected.po_reference
        if receipt.vendor is None:
            receipt.vendor = expected.vendor
        if receipt.currency is None:
            receipt.currency = expected.currency
        if receipt.receipt_status is None:
            receipt.receipt_status = "SUCCESS"

        policy_rules = None
        if self._policy_retrieval is not None and tenant_id is not None:
            try:
                snapshot = await self._policy_retrieval.build_risk_snapshot(
                    tenant_id=tenant_id,
                    purchase_amount=expected.amount,
                )
                policy_rules = snapshot.rules
            except Exception:
                policy_rules = None

        amount_tolerance = tolerance_from_policy_rules(policy_rules)
        result = three_way_match(
            po=expected,
            receipt=receipt,
            invoice=invoice,
            amount_tolerance=amount_tolerance,
        )
        match_payload = {
            "invoice_match_status": result.status,
            "message": result.message,
            "compared_fields": result.compared_fields,
            "mismatches": result.mismatches,
            "three_way": result.three_way,
            "amount_tolerance": str(amount_tolerance),
            "notes": invoice.notes or None,
        }

        if result.status == INSUFFICIENT_EVIDENCE:
            return WorkflowResult(
                process_id=process_id,
                current_stage=stage,
                success=False,
                message=result.message,
                error_code="INVOICE_INSUFFICIENT_EVIDENCE",
                error_message=result.message,
                agent_response=match_payload,
            )

        if result.status == MISMATCH:
            if self._exceptions is not None:
                failure = await self.capture_failure(
                    process_id,
                    description=(
                        "Invoice matching failed: "
                        + "; ".join(result.mismatches)
                    ),
                    severity=ExceptionSeverity.HIGH,
                    exception_type=ExceptionType.SYSTEM_ERROR,
                )
                return failure.model_copy(
                    update={
                        "success": False,
                        "message": result.message,
                        "error_code": "INVOICE_MISMATCH",
                        "error_message": result.message,
                        "agent_response": match_payload,
                    }
                )
            return WorkflowResult(
                process_id=process_id,
                current_stage=stage,
                success=False,
                message=result.message,
                error_code="INVOICE_MISMATCH",
                error_message=result.message,
                agent_response=match_payload,
            )

        reason = "Invoice matched expected purchase data"
        if invoice.notes:
            reason = f"{reason}: {invoice.notes}"
        await self._orchestrator.move_process(
            process_id,
            WorkflowStage.COMPLETED,
            reason=reason,
            transition_context=TransitionContext(invoice_match_status="MATCHED"),
        )
        stage = await self._orchestrator.get_current_stage(process_id)
        return WorkflowResult(
            process_id=process_id,
            current_stage=stage,
            success=True,
            message=result.message,
            agent_response=match_payload,
        )

    async def _request_discovery(self, process_id: UUID) -> WorkflowResult:
        return await self._send_to_agent(
            process_id=process_id,
            receiver=AGENT_1,
            message_type=AgentMessageType.PROCESS_DISCOVERY_REQUEST,
            payload={},
            success_type=AgentMessageType.PROCESS_DISCOVERY_RESPONSE,
            unavailable_message="Agent 1 process discovery is unavailable",
        )

    async def _send_to_agent(
        self,
        process_id: UUID,
        receiver: str,
        message_type: AgentMessageType,
        payload: dict,
        success_type: AgentMessageType,
        unavailable_message: str,
        task_id: UUID | None = None,
        tenant_id: UUID | None = None,
        correlation_id: UUID | None = None,
        message_status: str | None = None,
    ) -> WorkflowResult:
        stage = await self._orchestrator.get_current_stage(process_id)
        message = AgentMessage(
            metadata=AgentMessageMetadata(
                correlation_id=correlation_id or uuid4(),
                process_instance_id=process_id,
                task_id=task_id,
                tenant_id=tenant_id,
                sender=AGENT_4,
                receiver=receiver,
                message_type=message_type,
            ),
            payload=payload,
            status=message_status,
        )
        try:
            response = await self._communication.send(message)
        except AgentUnavailableError as exc:
            return WorkflowResult(
                process_id=process_id,
                current_stage=stage,
                success=False,
                message=unavailable_message,
                error_code="AGENT_UNAVAILABLE",
                error_message=str(exc),
            )
        except CommunicationFailureError as exc:
            return WorkflowResult(
                process_id=process_id,
                current_stage=stage,
                success=False,
                message="Agent communication failed",
                error_code="COMMUNICATION_FAILURE",
                error_message=str(exc),
            )
        except (InvalidMessageError, UnsupportedAgentError) as exc:
            return WorkflowResult(
                process_id=process_id,
                current_stage=stage,
                success=False,
                message="Invalid agent message",
                error_code="INVALID_MESSAGE",
                error_message=str(exc),
            )

        succeeded = response.metadata.message_type is success_type
        return WorkflowResult(
            process_id=process_id,
            current_stage=stage,
            success=succeeded,
            message=(
                f"Received {response.metadata.message_type.value} from {receiver}"
            ),
            error_code=None if succeeded else str(response.metadata.message_type.value),
            error_message=None if succeeded else str(response.payload),
            agent_response=dict(response.payload),
        )
