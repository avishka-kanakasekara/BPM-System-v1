"""Higher-level BPM orchestration coordinator for Agent 4.

Coordinates OrchestratorService, RiskAnalysisEngine, ApprovalService, and
AgentCommunicationService. Does not contain SQL, transition tables, risk
rules, or allocation logic.
"""

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
from .risk_rules import RiskAnalysisEngine
from .schemas import (
    ApprovalRequestRecord,
    RiskAssessment,
    RiskEvaluationContext,
    WorkflowResult,
)
from .service import OrchestratorService
from .state_machine import InvalidTransitionError


class Agent4Workflow:
    """Coordinates the BPM lifecycle. State changes go through OrchestratorService."""

    def __init__(
        self,
        orchestrator: OrchestratorService,
        risk_engine: RiskAnalysisEngine | None = None,
        approval_service: ApprovalService | None = None,
        communication: AgentCommunicationService | None = None,
        exception_service: ExceptionService | None = None,
    ) -> None:
        if approval_service is None:
            raise ValueError("ApprovalService is required for Agent4Workflow")
        self._orchestrator = orchestrator
        self._risk_engine = risk_engine or RiskAnalysisEngine()
        self._approvals = approval_service
        self._communication = communication or AgentCommunicationService()
        self._exceptions = exception_service

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
        RESOURCE_PLANNING with an honest error result.
        """
        await self._orchestrator.move_process(
            process_id,
            WorkflowStage.RESOURCE_PLANNING,
            reason="Begin resource planning with Agent 3",
        )
        result = await self.plan_resources(
            process_id,
            payload=payload,
            task_id=task_id,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )
        if not result.success:
            return result

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
    ) -> WorkflowResult:
        """Run the risk engine at RISK_REVIEW and open an approval gate if needed."""
        assessment = self._risk_engine.evaluate(context)
        try:
            if self._approvals.requires_human_approval(assessment):
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
                    message="Human approval required",
                    human_approval_required=True,
                    approval=gate.approval,
                    risk_assessment=assessment,
                    eligible_for_execution=False,
                )

            await self._orchestrator.move_process(
                process_id,
                WorkflowStage.WORKFLOW_EXECUTION,
                reason="No human-approval risk findings",
            )
            stage = await self._orchestrator.get_current_stage(process_id)
            return WorkflowResult(
                process_id=process_id,
                current_stage=stage,
                success=True,
                message="No human approval required; process is eligible for execution",
                human_approval_required=False,
                risk_assessment=assessment,
                eligible_for_execution=True,
            )
        except InvalidTransitionError:
            raise
        except (DatabasePersistenceError, ProcessNotFoundError):
            raise

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
        WORKFLOW_EXECUTION → INVOICE_MATCHING. On a failed/blocked receipt or
        unreachable Agent 2, a BPM exception is recorded (which halts the
        process via the StateMachine when allowed).
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
            )
            stage = await self._orchestrator.get_current_stage(process_id)
            return result.model_copy(update={"current_stage": stage})

        failure_detail = (
            result.error_message
            or (result.agent_response or {}).get("error_message")
            or f"Agent 2 execution did not succeed (receipt_status={receipt_status or 'UNKNOWN'})"
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

    async def complete_invoice_matching(
        self,
        process_id: UUID,
        reference: str = "",
    ) -> WorkflowResult:
        """INVOICE_MATCHING → COMPLETED as an explicit, deliberate closure.

        No automated invoice-matching logic exists yet; closing the stage is
        an explicit API action with an operator-supplied reference, never an
        implicit auto-complete.
        """
        reason = "Invoice matching closed"
        if reference:
            reason = f"Invoice matching closed: {reference}"
        await self._orchestrator.move_process(
            process_id,
            WorkflowStage.COMPLETED,
            reason=reason,
        )
        stage = await self._orchestrator.get_current_stage(process_id)
        return WorkflowResult(
            process_id=process_id,
            current_stage=stage,
            success=True,
            message="Process completed",
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
