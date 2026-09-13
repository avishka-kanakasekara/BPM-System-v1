"""Agent 4 policy-driven integration scenarios (A–J style)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents.agent4_orchestrator import (
    Agent4Workflow,
    ApprovalService,
    ApprovalStatus,
    InMemoryApprovalRepository,
    OrchestratorService,
    RiskEvaluationContext,
    RiskType,
    WorkflowStage,
)
from app.agents.agent4_orchestrator.exception_repository import InMemoryExceptionRepository
from app.agents.agent4_orchestrator.exception_service import ExceptionService
from app.policy_knowledge import (
    PolicyCategory,
    PolicyCreateRequest,
    PolicyIngestionService,
    PolicyRetrievalService,
    PolicyRule,
    PolicyRuleType,
)
from app.policy_knowledge.constants import PolicyOperator
from app.policy_knowledge.repository import InMemoryPolicyRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def harness():
    repo = InMemoryPolicyRepository()
    ingestion = PolicyIngestionService(repo)
    retrieval = PolicyRetrievalService(repo)
    orchestrator = OrchestratorService()
    approval_repo = InMemoryApprovalRepository()
    approvals = ApprovalService(orchestrator, approval_repo)
    exceptions = ExceptionService(orchestrator, InMemoryExceptionRepository())
    workflow = Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=approvals,
        exception_service=exceptions,
        policy_retrieval=retrieval,
    )
    return {
        "tenant": uuid4(),
        "ingestion": ingestion,
        "retrieval": retrieval,
        "orchestrator": orchestrator,
        "approvals": approvals,
        "approval_repo": approval_repo,
        "workflow": workflow,
    }


async def _seed(harness, *, threshold="1000000", name="Procurement Policy", version="2026.1"):
    return await harness["ingestion"].ingest(
        tenant_id=harness["tenant"],
        uploaded_by=uuid4(),
        request=PolicyCreateRequest(
            name=name,
            category=PolicyCategory.PROCUREMENT,
            version_label=version,
            activate=True,
            text_content=(
                f"Purchases above {threshold} LKR require Senior Management approval.\n"
                "A quotation is required."
            ),
            rules=[
                PolicyRule(
                    rule_type=PolicyRuleType.APPROVAL_THRESHOLD,
                    operator=PolicyOperator.GT,
                    threshold_value=Decimal(threshold),
                    currency="LKR",
                    required_approval="SENIOR_MANAGEMENT",
                ),
                PolicyRule(
                    rule_type=PolicyRuleType.REQUIRED_EVIDENCE,
                    required_evidence=["quotation"],
                ),
            ],
        ),
    )


async def _at_risk_review(harness):
    process_id = uuid4()
    await harness["orchestrator"].create_process(
        process_id, initial_stage=WorkflowStage.RISK_REVIEW
    )
    return process_id


class TestAgent4PolicyScenarios:
    async def test_scenario_a_high_value_requires_approval(self, harness) -> None:
        await _seed(harness, threshold="1000000")
        process_id = await _at_risk_review(harness)
        result = await harness["workflow"].handle_risk(
            process_id,
            RiskEvaluationContext(
                purchase_amount=Decimal("1500000"),
                currency="LKR",
                provided_evidence=["quotation"],
            ),
            tenant_id=harness["tenant"],
        )
        assert result.human_approval_required is True
        assert result.current_stage is WorkflowStage.AWAITING_HUMAN_APPROVAL
        types = {f.risk_type for f in result.risk_assessment.findings}
        assert RiskType.HIGH_VALUE_PURCHASE in types

    async def test_scenario_b_below_threshold_no_high_value(self, harness) -> None:
        await _seed(harness, threshold="1000000")
        process_id = await _at_risk_review(harness)
        result = await harness["workflow"].handle_risk(
            process_id,
            RiskEvaluationContext(
                purchase_amount=Decimal("500000"),
                currency="LKR",
                provided_evidence=["quotation"],
            ),
            tenant_id=harness["tenant"],
        )
        types = {f.risk_type for f in (result.risk_assessment.findings if result.risk_assessment else [])}
        assert RiskType.HIGH_VALUE_PURCHASE not in types
        assert RiskType.UNAUTHORIZED_ACTION not in types
        assert result.human_approval_required is False
        assert result.current_stage is WorkflowStage.WORKFLOW_EXECUTION
        assert result.eligible_for_execution is True

    async def test_scenario_c_budget_failure(self, harness) -> None:
        await _seed(harness)
        process_id = await _at_risk_review(harness)
        result = await harness["workflow"].handle_risk(
            process_id,
            RiskEvaluationContext(
                purchase_amount=Decimal("1500000"),
                available_budget=Decimal("1000000"),
                provided_evidence=["quotation"],
            ),
            tenant_id=harness["tenant"],
        )
        types = {f.risk_type for f in result.risk_assessment.findings}
        assert RiskType.BUDGET_VALIDATION_FAILURE in types
        assert result.human_approval_required is True

    async def test_scenario_d_missing_quotation(self, harness) -> None:
        await _seed(harness)
        process_id = await _at_risk_review(harness)
        result = await harness["workflow"].handle_risk(
            process_id,
            RiskEvaluationContext(
                purchase_amount=Decimal("100"),
                provided_evidence=[],
            ),
            tenant_id=harness["tenant"],
        )
        types = {f.risk_type for f in result.risk_assessment.findings}
        assert RiskType.MISSING_EVIDENCE in types
        assert result.human_approval_required is True
        assert result.current_stage is WorkflowStage.AWAITING_HUMAN_APPROVAL

    async def test_scenario_e_policy_uncertainty(self, harness) -> None:
        process_id = await _at_risk_review(harness)
        result = await harness["workflow"].handle_risk(
            process_id,
            RiskEvaluationContext(purchase_amount=Decimal("1500000")),
            tenant_id=harness["tenant"],
        )
        types = {f.risk_type for f in result.risk_assessment.findings}
        assert RiskType.POLICY_UNCERTAINTY in types
        assert RiskType.HIGH_VALUE_PURCHASE not in types
        assert result.human_approval_required is True

    async def test_scenario_f_policy_conflict(self, harness) -> None:
        await _seed(harness, threshold="1000000", name="Policy A", version="A")
        await harness["ingestion"].ingest(
            tenant_id=harness["tenant"],
            uploaded_by=uuid4(),
            request=PolicyCreateRequest(
                name="Policy B",
                category=PolicyCategory.PROCUREMENT,
                version_label="B",
                activate=True,
                text_content="Purchases above 500000 LKR require Finance approval.",
                rules=[
                    PolicyRule(
                        rule_type=PolicyRuleType.APPROVAL_THRESHOLD,
                        threshold_value=Decimal("500000"),
                        currency="LKR",
                        required_approval="FINANCE",
                    )
                ],
            ),
        )
        process_id = await _at_risk_review(harness)
        result = await harness["workflow"].handle_risk(
            process_id,
            RiskEvaluationContext(purchase_amount=Decimal("1500000")),
            tenant_id=harness["tenant"],
        )
        types = {f.risk_type for f in result.risk_assessment.findings}
        assert RiskType.POLICY_CONFLICT in types
        assert result.human_approval_required is True

    async def test_scenario_g_human_reject_blocks_execution(self, harness) -> None:
        await _seed(harness)
        process_id = await _at_risk_review(harness)
        gate = await harness["workflow"].handle_risk(
            process_id,
            RiskEvaluationContext(
                purchase_amount=Decimal("1500000"),
                provided_evidence=["quotation"],
            ),
            tenant_id=harness["tenant"],
        )
        assert gate.approval is not None
        decided = await harness["approvals"].reject_request(
            gate.approval.id, approver_id=uuid4(), comments="Denied"
        )
        outcome = await harness["workflow"].apply_approval_outcome(
            process_id, decided.approval
        )
        assert outcome.current_stage is WorkflowStage.EXCEPTION
        assert outcome.eligible_for_execution is False

    async def test_scenario_h_human_approve_allows_execution_stage(self, harness) -> None:
        from unittest.mock import AsyncMock, patch

        from app.schemas.agent_message import (
            AGENT_2,
            AGENT_4,
            AgentMessage,
            AgentMessageMetadata,
            AgentMessageType,
        )

        await _seed(harness)
        process_id = await _at_risk_review(harness)
        gate = await harness["workflow"].handle_risk(
            process_id,
            RiskEvaluationContext(
                purchase_amount=Decimal("1500000"),
                provided_evidence=["quotation"],
            ),
            tenant_id=harness["tenant"],
        )
        assert gate.approval is not None
        decided = await harness["approvals"].approve_request(
            gate.approval.id, approver_id=uuid4(), comments="OK"
        )
        assert decided.approval.status is ApprovalStatus.APPROVED

        def _agent2_ok(message):
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
                status="AUTHORIZED",
            )

        with patch(
            "app.agents.agent4_orchestrator.communication_service.AgentCommunicationService.send",
            new_callable=AsyncMock,
            side_effect=_agent2_ok,
        ):
            outcome = await harness["workflow"].apply_approval_outcome(
                process_id, decided.approval
            )
        assert outcome.eligible_for_execution is True
        assert outcome.current_stage is WorkflowStage.WORKFLOW_EXECUTION

    async def test_scenario_i_invoice_match_completes(self, harness) -> None:
        from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID
        from app.tests.test_phase8c_invoice_matching import _invoice, _po

        process_id = uuid4()
        await harness["orchestrator"].create_process(
            process_id, initial_stage=WorkflowStage.INVOICE_MATCHING
        )
        po = _po(process_id=process_id)
        _invoice(process_id=process_id, po_id=po.purchase_order_id, number="INV-100")
        result = await harness["workflow"].complete_invoice_matching(
            process_id,
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            invoice_number="INV-100",
        )
        assert result.success is True
        assert result.current_stage is WorkflowStage.COMPLETED

    async def test_scenario_j_invoice_mismatch_exception(self, harness) -> None:
        from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID
        from app.tests.test_phase8c_invoice_matching import _invoice, _po

        process_id = uuid4()
        await harness["orchestrator"].create_process(
            process_id, initial_stage=WorkflowStage.INVOICE_MATCHING
        )
        po = _po(process_id=process_id)
        _invoice(
            process_id=process_id,
            po_id=po.purchase_order_id,
            number="INV-100-MIS",
            total="1600000",
            subtotal="1600000",
            qty="20",
            unit="80000",
        )
        result = await harness["workflow"].complete_invoice_matching(
            process_id,
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            invoice_number="INV-100-MIS",
        )
        assert result.success is False
        assert result.error_code == "AMOUNT_MISMATCH"
        assert result.current_stage is WorkflowStage.EXCEPTION
