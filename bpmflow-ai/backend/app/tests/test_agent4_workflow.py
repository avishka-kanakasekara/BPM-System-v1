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
        self, workflow, orchestrator
    ) -> None:
        process_id = uuid4()
        await orchestrator.create_process(
            process_id, initial_stage=WorkflowStage.WORKFLOW_EXECUTION
        )
        result = await workflow.execute_workflow(process_id)
        assert result.success is False
        assert result.error_code == "AGENT_UNAVAILABLE"
        assert "Agent 2" in result.message
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
