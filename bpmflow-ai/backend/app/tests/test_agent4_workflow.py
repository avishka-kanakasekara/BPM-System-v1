"""Tests for Agent 4 BPM orchestration workflow coordinator."""

from decimal import Decimal
from uuid import uuid4

import inspect
import pytest

from app.agents.agent4_orchestrator import (
    Agent4Workflow,
    AgentCommunicationService,
    ApprovalService,
    ApprovalStatus,
    InMemoryApprovalRepository,
    InvalidTransitionError,
    OrchestratorService,
    RiskEvaluationContext,
    WorkflowStage,
)
from app.agents.agent4_orchestrator.adapters import Agent3Adapter
from app.schemas.agent_message import AGENT_3, AgentMessageType

pytestmark = pytest.mark.asyncio


@pytest.fixture
def orchestrator() -> OrchestratorService:
    return OrchestratorService()


@pytest.fixture
def approval_repo() -> InMemoryApprovalRepository:
    return InMemoryApprovalRepository()


@pytest.fixture
def workflow(orchestrator, approval_repo) -> Agent4Workflow:
    return Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=ApprovalService(orchestrator, approval_repo),
        communication=AgentCommunicationService(),
    )


class TestStartAndDiscovery:
    async def test_start_process_moves_to_discovering(self, workflow, orchestrator) -> None:
        process_id = uuid4()
        result = await workflow.start_process(process_id)
        assert result.current_stage is WorkflowStage.DISCOVERING
        assert await orchestrator.get_current_stage(process_id) is WorkflowStage.DISCOVERING

    async def test_discovery_unavailable_is_not_fake_success(
        self, workflow, orchestrator
    ) -> None:
        process_id = uuid4()
        result = await workflow.start_process(process_id)
        assert result.success is False
        assert result.error_code == "AGENT_UNAVAILABLE"
        assert "Agent 1" in result.message
        assert result.current_stage is WorkflowStage.DISCOVERING
        assert await orchestrator.get_current_stage(process_id) is WorkflowStage.DISCOVERING


class TestResourcePlanningBoundary:
    async def test_resource_planning_uses_agent3_communication(
        self, orchestrator, approval_repo
    ) -> None:
        process_id = uuid4()
        adapter = Agent3Adapter()
        workflow = Agent4Workflow(
            orchestrator=orchestrator,
            approval_service=ApprovalService(orchestrator, approval_repo),
            communication=AgentCommunicationService(adapters={AGENT_3: adapter}),
        )
        await orchestrator.create_process(
            process_id, initial_stage=WorkflowStage.RESOURCE_PLANNING
        )
        result = await workflow.plan_resources(
            process_id,
            payload={"human_requirements": {"required_roles": ["approver"]}},
        )

        assert adapter.last_message is not None
        assert adapter.last_message.metadata.receiver == AGENT_3
        assert adapter.last_message.metadata.message_type is (
            AgentMessageType.RESOURCE_ALLOCATION_REQUEST
        )
        assert result.success is False
        assert result.error_code == AgentMessageType.ERROR.value
        assert "ranked" not in result.message.lower()
        assert "eligible_candidates" not in (result.error_message or "")


class TestRiskAndApproval:
    async def test_no_risk_review_moves_toward_workflow_execution(
        self, workflow, orchestrator
    ) -> None:
        process_id = uuid4()
        await orchestrator.create_process(
            process_id, initial_stage=WorkflowStage.RISK_REVIEW
        )
        result = await workflow.handle_risk(process_id, RiskEvaluationContext())
        assert result.success is True
        assert result.human_approval_required is False
        assert result.current_stage is WorkflowStage.WORKFLOW_EXECUTION
        assert result.eligible_for_execution is True

    async def test_high_value_purchase_requires_approval(
        self, workflow, orchestrator
    ) -> None:
        process_id = uuid4()
        await orchestrator.create_process(
            process_id, initial_stage=WorkflowStage.RISK_REVIEW
        )
        result = await workflow.handle_risk(
            process_id,
            RiskEvaluationContext(purchase_amount=Decimal("25000")),
        )
        assert result.human_approval_required is True
        assert result.approval is not None
        assert result.approval.status is ApprovalStatus.PENDING
        assert result.current_stage is WorkflowStage.AWAITING_HUMAN_APPROVAL
        assert await orchestrator.get_current_stage(process_id) is (
            WorkflowStage.AWAITING_HUMAN_APPROVAL
        )

    async def test_pending_approval_does_not_continue_execution(
        self, workflow, orchestrator
    ) -> None:
        process_id = uuid4()
        await orchestrator.create_process(
            process_id, initial_stage=WorkflowStage.RISK_REVIEW
        )
        gate = await workflow.handle_risk(
            process_id,
            RiskEvaluationContext(purchase_amount=Decimal("25000")),
        )
        result = await workflow.apply_approval_outcome(process_id, gate.approval)
        assert result.eligible_for_execution is False
        assert result.current_stage is WorkflowStage.AWAITING_HUMAN_APPROVAL
        assert await orchestrator.get_current_stage(process_id) is (
            WorkflowStage.AWAITING_HUMAN_APPROVAL
        )

    async def test_rejected_approval_moves_to_exception(
        self, workflow, orchestrator, approval_repo
    ) -> None:
        process_id = uuid4()
        approvals = ApprovalService(orchestrator, approval_repo)
        workflow = Agent4Workflow(
            orchestrator=orchestrator,
            approval_service=approvals,
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
        assert await orchestrator.get_current_stage(process_id) is WorkflowStage.EXCEPTION
        assert result.eligible_for_execution is False


class TestExecutionAndInvalid:
    async def test_agent2_unavailable_is_handled_cleanly(
        self, orchestrator, approval_repo
    ) -> None:
        """A broken Agent 2 pipeline yields an honest ERROR envelope, not a crash."""
        from app.agents.agent4_orchestrator.adapters import Agent2Adapter
        from app.schemas.agent_message import AGENT_2

        class BrokenAgent2:
            async def handle(self, message, session=None):
                raise RuntimeError("execution pipeline down")

        workflow = Agent4Workflow(
            orchestrator=orchestrator,
            approval_service=ApprovalService(orchestrator, approval_repo),
            communication=AgentCommunicationService(
                adapters={AGENT_2: Agent2Adapter(agent=BrokenAgent2())}
            ),
        )
        process_id = uuid4()
        await orchestrator.create_process(
            process_id, initial_stage=WorkflowStage.WORKFLOW_EXECUTION
        )
        result = await workflow.execute_workflow(process_id)
        assert result.success is False
        assert result.error_code == "ERROR"
        assert "agent2" in result.message.lower().replace("_", "")
        assert result.agent_response is not None
        assert result.agent_response.get("receipt_status") == "FAILED"
        assert result.current_stage is WorkflowStage.WORKFLOW_EXECUTION

    async def test_invalid_transitions_are_rejected(
        self, workflow, orchestrator
    ) -> None:
        process_id = uuid4()
        await workflow.start_process(process_id)
        with pytest.raises(InvalidTransitionError):
            await workflow.advance_process(
                process_id,
                WorkflowStage.COMPLETED,
                reason="Skip ahead",
            )
        assert await orchestrator.get_current_stage(process_id) is WorkflowStage.DISCOVERING

    async def test_statemachine_remains_source_of_truth(
        self, workflow, orchestrator
    ) -> None:
        process_id = uuid4()
        await orchestrator.create_process(process_id, initial_stage=WorkflowStage.DRAFT)
        assert await orchestrator.can_move(process_id, WorkflowStage.DISCOVERING) is True
        assert await orchestrator.can_move(process_id, WorkflowStage.COMPLETED) is False
        import app.agents.agent4_orchestrator.workflow as workflow_mod

        source = inspect.getsource(workflow_mod)
        assert "ALLOWED_TRANSITIONS" not in source
        assert "HIGH_VALUE_PURCHASE_THRESHOLD" not in source

    async def test_approved_outcome_dispatches_agent2(
        self, orchestrator, approval_repo
    ) -> None:
        from app.agents.agent4_orchestrator.communication import AgentAdapter
        from app.schemas.agent_message import (
            AGENT_2,
            AGENT_4,
            AgentMessage,
            AgentMessageMetadata,
            AgentMessageType,
        )

        captured: list[AgentMessage] = []

        class AuthorizedAgent2(AgentAdapter):
            async def send(self, message: AgentMessage) -> AgentMessage:
                captured.append(message)
                return AgentMessage(
                    metadata=AgentMessageMetadata(
                        correlation_id=message.metadata.correlation_id,
                        process_instance_id=message.metadata.process_instance_id,
                        task_id=message.metadata.task_id,
                        sender=AGENT_2,
                        receiver=AGENT_4,
                        message_type=AgentMessageType.WORKFLOW_EXECUTION_RESPONSE,
                    ),
                    payload={"receipt_status": "SUCCESS"},
                )

        workflow = Agent4Workflow(
            orchestrator=orchestrator,
            approval_service=ApprovalService(orchestrator, approval_repo),
            communication=AgentCommunicationService(adapters={AGENT_2: AuthorizedAgent2()}),
        )
        process_id = uuid4()
        await orchestrator.create_process(
            process_id, initial_stage=WorkflowStage.RISK_REVIEW
        )
        gate = await workflow.handle_risk(
            process_id,
            RiskEvaluationContext(purchase_amount=Decimal("25000")),
        )
        approvals = ApprovalService(orchestrator, approval_repo)
        decided = await approvals.approve_request(
            gate.approval.id, approver_id=uuid4()
        )
        result = await workflow.apply_approval_outcome(process_id, decided.approval)
        assert captured and captured[0].status == "AUTHORIZED"
        assert result.current_stage is WorkflowStage.INVOICE_MATCHING
        assert result.eligible_for_execution is True

    async def test_complete_invoice_matching_requires_real_match(
        self, workflow, orchestrator
    ) -> None:
        process_id = uuid4()
        await orchestrator.create_process(
            process_id, initial_stage=WorkflowStage.INVOICE_MATCHING
        )
        insufficient = await workflow.complete_invoice_matching(
            process_id, reference="INV-9"
        )
        assert insufficient.success is False
        assert insufficient.error_code == "INVOICE_INSUFFICIENT_EVIDENCE"
        assert await orchestrator.get_current_stage(process_id) is WorkflowStage.INVOICE_MATCHING

        matched = await workflow.complete_invoice_matching(
            process_id,
            amount=100.0,
            expected_amount=100.0,
            po_reference="PO-1",
            expected_po_reference="PO-1",
            notes="INV-9",
        )
        assert matched.success is True
        assert matched.current_stage is WorkflowStage.COMPLETED
        assert await orchestrator.get_current_stage(process_id) is WorkflowStage.COMPLETED
