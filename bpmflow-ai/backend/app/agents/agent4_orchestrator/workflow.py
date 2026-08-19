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
        correlation_id: UUID | None = None,
    ) -> WorkflowResult:
        """Send a resource-allocation request through the Agent 3 adapter boundary."""
        return await self._send_to_agent(
            process_id=process_id,
            receiver=AGENT_3,
            message_type=AgentMessageType.RESOURCE_ALLOCATION_REQUEST,
            payload=payload or {},
            task_id=task_id,
            correlation_id=correlation_id,
            success_type=AgentMessageType.RESOURCE_ALLOCATION_RESPONSE,
            unavailable_message="Agent 3 resource planning is unavailable",
        )

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
    ) -> WorkflowResult:
        """Interpret PENDING / APPROVED / REJECTED. Does not start Agent 2."""
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
            return WorkflowResult(
                process_id=process_id,
                current_stage=stage,
                success=True,
                message="Approval granted; process is eligible for workflow execution",
                approval=approval,
                eligible_for_execution=True,
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
        """Request Agent 2 execution. Does not fake success if Agent 2 is unavailable."""
        return await self._send_to_agent(
            process_id=process_id,
            receiver=AGENT_2,
            message_type=AgentMessageType.WORKFLOW_EXECUTION_REQUEST,
            payload=payload or {},
            task_id=task_id,
            correlation_id=correlation_id,
            success_type=AgentMessageType.WORKFLOW_EXECUTION_RESPONSE,
            unavailable_message="Agent 2 workflow execution is unavailable",
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
        correlation_id: UUID | None = None,
    ) -> WorkflowResult:
        stage = await self._orchestrator.get_current_stage(process_id)
        message = AgentMessage(
            metadata=AgentMessageMetadata(
                correlation_id=correlation_id or uuid4(),
                process_instance_id=process_id,
                task_id=task_id,
                sender=AGENT_4,
                receiver=receiver,
                message_type=message_type,
            ),
            payload=payload,
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
        )
