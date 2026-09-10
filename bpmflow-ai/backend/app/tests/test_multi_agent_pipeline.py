"""End-to-end procurement pipeline across real Agent 4 orchestration.

Uses in-process adapters that implement the real Agent 1 / 2 / 3 contracts
(no mock_agent4, no fabricated success). A single correlation_id is
preserved on every hop.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents.agent4_orchestrator import (
    Agent4Workflow,
    AgentCommunicationService,
    ApprovalService,
    ApprovalStatus,
    InMemoryApprovalRepository,
    OrchestratorService,
    RiskEvaluationContext,
    WorkflowStage,
)
from app.agents.agent4_orchestrator.communication import AgentAdapter
from app.agents.agent4_orchestrator.exception_repository import InMemoryExceptionRepository
from app.agents.agent4_orchestrator.exception_service import ExceptionService
from app.schemas.agent_message import (
    AGENT_1,
    AGENT_2,
    AGENT_3,
    AGENT_4,
    AgentMessage,
    AgentMessageMetadata,
    AgentMessageType,
)

pytestmark = pytest.mark.asyncio


def _reply(
    request: AgentMessage,
    sender: str,
    message_type: AgentMessageType,
    payload: dict,
    *,
    status: str | None = None,
    confidence: float | None = None,
    evidence_refs: list[str] | None = None,
) -> AgentMessage:
    return AgentMessage(
        metadata=AgentMessageMetadata(
            correlation_id=request.metadata.correlation_id,
            process_instance_id=request.metadata.process_instance_id,
            task_id=request.metadata.task_id,
            tenant_id=request.metadata.tenant_id,
            sender=sender,
            receiver=AGENT_4,
            message_type=message_type,
        ),
        payload=payload,
        status=status,
        confidence=confidence,
        evidence_refs=evidence_refs or [],
    )


class RecordingDiscoveryAdapter(AgentAdapter):
    """Stands in for persisted Agent 1 discovery — never writes approval fields."""

    def __init__(self) -> None:
        self.seen: list[AgentMessage] = []

    async def send(self, message: AgentMessage) -> AgentMessage:
        self.seen.append(message)
        payload = {
            "process_id": str(message.metadata.process_instance_id),
            "name": "Office supplies procurement",
            "process_type": "procurement",
            "discovery_status": "COMPLETE",
            "overall_confidence": 0.91,
            "process_json": {
                "steps": [
                    {"id": "request", "name": "Submit purchase request"},
                    {"id": "approve", "name": "Finance approval"},
                    {"id": "order", "name": "Raise purchase order"},
                ]
            },
        }
        assert "approved" not in payload
        assert "decision" not in payload
        assert "authorization" not in payload
        return _reply(
            message,
            AGENT_1,
            AgentMessageType.PROCESS_DISCOVERY_RESPONSE,
            payload,
            status="COMPLETE",
            confidence=0.91,
            evidence_refs=["doc:po-policy"],
        )


class RecordingAllocationAdapter(AgentAdapter):
    """Stands in for Agent 3 — never returns APPROVED/REJECTED."""

    def __init__(self) -> None:
        self.seen: list[AgentMessage] = []

    async def send(self, message: AgentMessage) -> AgentMessage:
        self.seen.append(message)
        assert message.metadata.task_id is not None
        assert message.metadata.tenant_id is not None
        return _reply(
            message,
            AGENT_3,
            AgentMessageType.RESOURCE_ALLOCATION_RESPONSE,
            {
                "recommendation_status": "PENDING_HUMAN_APPROVAL",
                "ranked_humans": [{"role": "approver", "score": 0.82}],
                "gaps": [],
            },
            status="PENDING_HUMAN_APPROVAL",
        )


class RecordingExecutionAdapter(AgentAdapter):
    """Stands in for Agent 2 — executes only AUTHORIZED messages."""

    def __init__(self) -> None:
        self.seen: list[AgentMessage] = []

    async def send(self, message: AgentMessage) -> AgentMessage:
        self.seen.append(message)
        if message.status != "AUTHORIZED":
            return _reply(
                message,
                AGENT_2,
                AgentMessageType.ERROR,
                {"error": "NOT_AUTHORIZED"},
            )
        return _reply(
            message,
            AGENT_2,
            AgentMessageType.WORKFLOW_EXECUTION_RESPONSE,
            {
                "receipt_status": "SUCCESS",
                "tools_executed": ["send_reminder_email"],
            },
            status="EXECUTION_RESULT",
            confidence=0.88,
            evidence_refs=["receipt:exec-1"],
        )


async def test_full_procurement_loop_preserves_correlation_id() -> None:
    correlation_id = uuid4()
    task_id = uuid4()
    tenant_id = uuid4()
    process_id = uuid4()

    discovery = RecordingDiscoveryAdapter()
    allocation = RecordingAllocationAdapter()
    execution = RecordingExecutionAdapter()

    orchestrator = OrchestratorService()
    approval_repo = InMemoryApprovalRepository()
    approvals = ApprovalService(orchestrator, approval_repo)
    exceptions = ExceptionService(orchestrator, InMemoryExceptionRepository())
    workflow = Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=approvals,
        exception_service=exceptions,
        communication=AgentCommunicationService(
            adapters={
                AGENT_1: discovery,
                AGENT_2: execution,
                AGENT_3: allocation,
            }
        ),
    )

    started = await workflow.start_process(process_id)
    assert started.success is True
    assert started.current_stage is WorkflowStage.DISCOVERING
    assert discovery.seen
    assert discovery.seen[0].metadata.correlation_id
    start_correlation = discovery.seen[0].metadata.correlation_id
    assert "approved" not in (started.agent_response or {})
    assert "decision" not in (started.agent_response or {})
    assert "authorization" not in (started.agent_response or {})

    planned = await workflow.run_resource_planning(
        process_id,
        payload={"human_requirements": {"required_roles": ["approver"]}},
        task_id=task_id,
        tenant_id=tenant_id,
        correlation_id=correlation_id,
    )
    assert planned.success is True
    assert planned.current_stage is WorkflowStage.RISK_REVIEW
    assert allocation.seen[0].metadata.correlation_id == correlation_id
    assert allocation.seen[0].metadata.task_id == task_id
    assert allocation.seen[0].metadata.tenant_id == tenant_id
    assert allocation.seen[0].metadata.process_instance_id == process_id
    assert (planned.agent_response or {}).get("recommendation_status") == (
        "PENDING_HUMAN_APPROVAL"
    )

    risk = await workflow.handle_risk(
        process_id,
        RiskEvaluationContext(purchase_amount=Decimal("25000")),
        task_id=task_id,
    )
    assert risk.human_approval_required is True
    assert risk.current_stage is WorkflowStage.AWAITING_HUMAN_APPROVAL
    assert risk.approval is not None
    assert risk.approval.status is ApprovalStatus.PENDING
    assert not execution.seen

    decided = await approvals.approve_request(risk.approval.id, approver_id=uuid4())
    executed = await workflow.apply_approval_outcome(
        process_id,
        decided.approval,
        execution_payload={"task_type": "EXECUTE_TASK", "note": "send reminder"},
        correlation_id=correlation_id,
    )
    assert executed.success is True
    assert executed.current_stage is WorkflowStage.INVOICE_MATCHING
    assert len(execution.seen) == 1
    sent = execution.seen[0]
    assert sent.status == "AUTHORIZED"
    assert sent.metadata.correlation_id == correlation_id
    assert sent.metadata.process_instance_id == process_id
    assert sent.metadata.task_id == task_id
    assert (executed.agent_response or {}).get("receipt_status") == "SUCCESS"

    completed = await workflow.complete_invoice_matching(
        process_id,
        amount=10.0,
        expected_amount=10.0,
        po_reference="PO-DEMO",
        expected_po_reference="PO-DEMO",
        notes="INV-DEMO-1",
    )
    assert completed.success is True
    assert completed.current_stage is WorkflowStage.COMPLETED
    assert await orchestrator.get_current_stage(process_id) is WorkflowStage.COMPLETED

    # Discovery used its own generated correlation (start has no caller id);
    # every subsequent hop shares the explicit correlation_id.
    assert start_correlation is not None
    hop_ids = [
        allocation.seen[0].metadata.correlation_id,
        execution.seen[0].metadata.correlation_id,
    ]
    assert hop_ids == [correlation_id, correlation_id]


async def test_rejected_approval_never_reaches_agent2() -> None:
    process_id = uuid4()
    execution = RecordingExecutionAdapter()
    orchestrator = OrchestratorService()
    approval_repo = InMemoryApprovalRepository()
    approvals = ApprovalService(orchestrator, approval_repo)
    workflow = Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=approvals,
        communication=AgentCommunicationService(adapters={AGENT_2: execution}),
    )
    await orchestrator.create_process(
        process_id, initial_stage=WorkflowStage.RISK_REVIEW
    )
    gate = await workflow.handle_risk(
        process_id,
        RiskEvaluationContext(purchase_amount=Decimal("25000")),
    )
    decided = await approvals.reject_request(gate.approval.id, approver_id=uuid4())
    result = await workflow.apply_approval_outcome(process_id, decided.approval)
    assert result.current_stage is WorkflowStage.EXCEPTION
    assert execution.seen == []
