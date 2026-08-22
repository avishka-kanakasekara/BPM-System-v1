"""Tests for Agent 4 human approval gate."""

from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from app.agents.agent4_orchestrator import (
    ApprovalAlreadyDecidedError,
    ApprovalService,
    ApprovalStatus,
    InMemoryApprovalRepository,
    InvalidTransitionError,
    OrchestratorService,
    RiskAnalysisEngine,
    RiskEvaluationContext,
    RiskFinding,
    RiskLevel,
    RiskRecommendation,
    RiskType,
    WorkflowStage,
)
from app.agents.agent4_orchestrator.schemas import RiskAssessment

pytestmark = pytest.mark.asyncio


@pytest.fixture
def process_id():
    return uuid4()


@pytest_asyncio.fixture
async def orchestrator(process_id) -> OrchestratorService:
    service = OrchestratorService()
    await service.create_process(process_id, initial_stage=WorkflowStage.RISK_REVIEW)
    return service


@pytest.fixture
def approval_repo() -> InMemoryApprovalRepository:
    return InMemoryApprovalRepository()


@pytest.fixture
def approval_service(orchestrator, approval_repo) -> ApprovalService:
    return ApprovalService(orchestrator=orchestrator, repository=approval_repo)


def _assessment(*findings: RiskFinding, overall: RiskLevel | None = None) -> RiskAssessment:
    levels = [item.risk_level for item in findings]
    if overall is None and levels:
        rank = {
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
            RiskLevel.CRITICAL: 4,
        }
        overall = max(levels, key=lambda level: rank[level])
    return RiskAssessment(
        risk_detected=len(findings) > 0,
        overall_risk_level=overall,
        findings=list(findings),
    )


def _high_value_finding() -> RiskFinding:
    return RiskFinding(
        risk_level=RiskLevel.HIGH,
        risk_type=RiskType.HIGH_VALUE_PURCHASE,
        description="Purchase amount exceeds the high-value threshold.",
        recommendation=RiskRecommendation.HUMAN_APPROVAL,
    )


def _missing_evidence_finding() -> RiskFinding:
    return RiskFinding(
        risk_level=RiskLevel.MEDIUM,
        risk_type=RiskType.MISSING_EVIDENCE,
        description="Required evidence is missing: quote.",
        recommendation=RiskRecommendation.REQUEST_EVIDENCE,
    )


def _unauthorized_finding() -> RiskFinding:
    return RiskFinding(
        risk_level=RiskLevel.CRITICAL,
        risk_type=RiskType.UNAUTHORIZED_ACTION,
        description="The requested action is marked unauthorized.",
        recommendation=RiskRecommendation.BLOCK_ACTION,
    )


class TestApprovalCreation:
    async def test_human_approval_creates_pending_request(
        self,
        process_id,
        approval_repo,
        approval_service,
    ) -> None:
        result = await approval_service.apply_risk_assessment(
            process_id,
            _assessment(_high_value_finding()),
        )

        assert result.human_approval_required is True
        assert result.approval is not None
        assert result.approval.status is ApprovalStatus.PENDING
        assert result.approval.decision is None
        assert result.approval.decided_at is None
        pending = await approval_service.get_pending_approval_for_process(process_id)
        assert pending is not None
        assert pending.id == result.approval.id
        assert approval_repo.audit_events[0]["action"] == "created"

    async def test_process_moves_to_awaiting_human_approval(
        self,
        process_id,
        orchestrator,
        approval_service,
    ) -> None:
        result = await approval_service.apply_risk_assessment(
            process_id,
            _assessment(_high_value_finding()),
        )

        assert await orchestrator.get_current_stage(process_id) is (
            WorkflowStage.AWAITING_HUMAN_APPROVAL
        )
        assert result.transition is not None
        assert result.transition.from_stage is WorkflowStage.RISK_REVIEW
        assert result.transition.to_stage is WorkflowStage.AWAITING_HUMAN_APPROVAL

    async def test_high_risk_is_stored(self, process_id, approval_service) -> None:
        result = await approval_service.apply_risk_assessment(
            process_id,
            _assessment(_high_value_finding()),
        )
        assert result.approval is not None
        assert result.approval.risk_level is RiskLevel.HIGH

    async def test_critical_risk_is_stored(self, process_id, approval_service) -> None:
        result = await approval_service.apply_risk_assessment(
            process_id,
            _assessment(_high_value_finding(), _unauthorized_finding()),
        )
        assert result.approval is not None
        assert result.approval.risk_level is RiskLevel.CRITICAL

    async def test_non_approval_risks_do_not_create_request(
        self,
        process_id,
        orchestrator,
        approval_service,
    ) -> None:
        result = await approval_service.apply_risk_assessment(
            process_id,
            _assessment(_missing_evidence_finding()),
        )
        assert result.human_approval_required is False
        assert result.approval is None
        assert await approval_service.get_pending_approval_for_process(process_id) is None
        assert await orchestrator.get_current_stage(process_id) is WorkflowStage.RISK_REVIEW

    async def test_approval_reason_contains_risk_information(
        self, process_id, approval_service
    ) -> None:
        result = await approval_service.apply_risk_assessment(
            process_id,
            _assessment(_high_value_finding(), _missing_evidence_finding()),
        )
        assert result.approval is not None
        assert "HIGH_VALUE_PURCHASE" in result.approval.reason
        assert "exceeds the high-value threshold" in result.approval.reason
        assert "MISSING_EVIDENCE" not in result.approval.reason

    async def test_invalid_stage_is_rejected_by_state_machine(
        self,
        approval_repo,
    ) -> None:
        process_id = uuid4()
        orchestrator = OrchestratorService()
        await orchestrator.create_process(process_id, initial_stage=WorkflowStage.DRAFT)
        service = ApprovalService(orchestrator=orchestrator, repository=approval_repo)

        with pytest.raises(InvalidTransitionError):
            await service.apply_risk_assessment(
                process_id,
                _assessment(_high_value_finding()),
            )
        assert await service.get_pending_approval_for_process(process_id) is None
        assert await orchestrator.get_current_stage(process_id) is WorkflowStage.DRAFT


class TestApprovalDecisions:
    async def test_pending_request_can_be_approved(
        self, process_id, approval_service
    ) -> None:
        gate = await approval_service.apply_risk_assessment(
            process_id,
            _assessment(_high_value_finding()),
        )
        approver_id = uuid4()
        created_at = gate.approval.created_at

        result = await approval_service.approve_request(
            gate.approval.id,
            approver_id=approver_id,
            comments="Approved for procurement",
        )

        approval = result.approval
        assert result.decision is ApprovalStatus.APPROVED
        assert approval.status is ApprovalStatus.APPROVED
        assert approval.decision is ApprovalStatus.APPROVED
        assert approval.approver_id == approver_id
        assert approval.comments == "Approved for procurement"
        assert approval.decided_at is not None
        assert approval.created_at == created_at

    async def test_pending_request_can_be_rejected(
        self, process_id, approval_service
    ) -> None:
        gate = await approval_service.apply_risk_assessment(
            process_id,
            _assessment(_high_value_finding()),
        )
        approver_id = uuid4()

        result = await approval_service.reject_request(
            gate.approval.id,
            approver_id=approver_id,
            comments="Over budget",
        )

        approval = result.approval
        assert result.decision is ApprovalStatus.REJECTED
        assert approval.status is ApprovalStatus.REJECTED
        assert approval.decision is ApprovalStatus.REJECTED
        assert approval.approver_id == approver_id
        assert approval.decided_at is not None

    async def test_already_decided_request_cannot_be_decided_again(
        self, process_id, approval_service, approval_repo
    ) -> None:
        gate = await approval_service.apply_risk_assessment(
            process_id,
            _assessment(_high_value_finding()),
        )
        await approval_service.approve_request(gate.approval.id, approver_id=uuid4())

        with pytest.raises(ApprovalAlreadyDecidedError):
            await approval_service.approve_request(gate.approval.id, approver_id=uuid4())
        with pytest.raises(ApprovalAlreadyDecidedError):
            await approval_service.reject_request(gate.approval.id, approver_id=uuid4())
        assert approval_repo.audit_events[-1]["action"] == "completed"

    async def test_engine_high_value_purchase_opens_gate(
        self, process_id, approval_service
    ) -> None:
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(purchase_amount=Decimal("25000"))
        )
        result = await approval_service.apply_risk_assessment(process_id, assessment)
        assert result.human_approval_required is True
        assert result.approval is not None
        assert result.approval.status is ApprovalStatus.PENDING
        assert result.approval.risk_level is RiskLevel.HIGH
