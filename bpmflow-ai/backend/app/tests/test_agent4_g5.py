"""G5: Agent 4 deterministic orchestration + policy-first risk."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents.agent4_orchestrator import (
    ApprovalService,
    InMemoryApprovalRepository,
    OrchestratorService,
    RiskAnalysisEngine,
    RiskEvaluationContext,
    RiskRecommendation,
    RiskType,
    WorkflowStage,
)
from app.agents.agent4_orchestrator.execution_payload import (
    ExecutionEnrichmentError,
    require_enrich_execute_parameters,
)
from app.agents.agent4_orchestrator.invoice_matching import (
    ExpectedPurchase,
    InvoiceEvidence,
    ReceiptEvidence,
    three_way_match,
)
from app.agents.agent4_orchestrator.risk_engine import (
    RISK_EVALUATORS,
    evaluate_policy_uncertainty,
)
from app.policy_knowledge import (
    PolicyCategory,
    PolicyCreateRequest,
    PolicyIngestionService,
    PolicyRetrievalService,
    PolicyRule,
    PolicyRuleType,
)
from app.policy_knowledge.constants import PolicyOperator, PolicyRetrievalStatus
from app.policy_knowledge.repository import InMemoryPolicyRepository


class TestG5RiskEngine:
    def test_ten_pure_evaluators_cover_all_risk_types(self) -> None:
        assert len(RISK_EVALUATORS) == 10

    @pytest.mark.asyncio
    async def test_policy_uncertainty_without_seed_policy(self) -> None:
        repo = InMemoryPolicyRepository()
        retrieval = PolicyRetrievalService(repo)
        tenant = uuid4()
        snapshot = await retrieval.build_risk_snapshot(
            tenant_id=tenant,
            purchase_amount=Decimal("5000"),
        )
        assert snapshot.status is PolicyRetrievalStatus.NOT_FOUND
        findings = evaluate_policy_uncertainty(
            RiskEvaluationContext(
                purchase_amount=Decimal("5000"),
                policy_snapshot=snapshot,
            )
        )
        assert findings
        assert findings[0].risk_type is RiskType.POLICY_UNCERTAINTY
        assert findings[0].recommendation is RiskRecommendation.HUMAN_APPROVAL

    @pytest.mark.asyncio
    async def test_threshold_from_policy_rules_not_legacy_constant(self) -> None:
        repo = InMemoryPolicyRepository()
        ingestion = PolicyIngestionService(repo)
        tenant = uuid4()
        await ingestion.ingest(
            tenant_id=tenant,
            uploaded_by=uuid4(),
            request=PolicyCreateRequest(
                name="Procurement",
                category=PolicyCategory.PROCUREMENT,
                version_label="1.0",
                activate=True,
                text_content="High value threshold 750000 LKR",
                rules=[
                    PolicyRule(
                        rule_type=PolicyRuleType.HIGH_VALUE_THRESHOLD,
                        operator=PolicyOperator.GT,
                        threshold_value=Decimal("750000"),
                        currency="LKR",
                    )
                ],
            ),
        )
        retrieval = PolicyRetrievalService(repo)
        snapshot = await retrieval.build_risk_snapshot(
            tenant_id=tenant,
            purchase_amount=Decimal("800000"),
        )
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                purchase_amount=Decimal("800000"),
                currency="LKR",
                policy_snapshot=snapshot,
            )
        )
        high_value = [
            f for f in assessment.findings if f.risk_type is RiskType.HIGH_VALUE_PURCHASE
        ]
        assert high_value
        assert high_value[0].threshold == Decimal("750000")
        assert "active company policy" in high_value[0].description

    @pytest.mark.asyncio
    async def test_vector_retrieval_prefers_embedded_chunks(self) -> None:
        repo = InMemoryPolicyRepository()
        ingestion = PolicyIngestionService(repo)
        tenant = uuid4()
        await ingestion.ingest(
            tenant_id=tenant,
            uploaded_by=uuid4(),
            request=PolicyCreateRequest(
                name="Finance",
                category=PolicyCategory.FINANCE,
                version_label="2026",
                activate=True,
                text_content="Invoice amount tolerance 0.50 for three-way matching.",
                rules=[
                    PolicyRule(
                        rule_type=PolicyRuleType.BUDGET_LIMIT,
                        metadata_json={"invoice_amount_tolerance": "0.50"},
                    )
                ],
            ),
        )
        retrieval = PolicyRetrievalService(repo)
        result = await retrieval.search(
            tenant_id=tenant,
            query="invoice three-way matching tolerance",
        )
        assert result.status is PolicyRetrievalStatus.FOUND
        assert result.evidence
        assert result.evidence[0].relevance_score > 0


class TestG5ExecutionEnrichment:
    def test_missing_discovery_metadata_does_not_invent_defaults(self) -> None:
        with pytest.raises(ExecutionEnrichmentError) as exc:
            require_enrich_execute_parameters(
                process_id=str(uuid4()),
                process_type="PROCUREMENT",
                process_name="Test",
                metadata_json={},
                parameters={},
            )
        assert "purchase.amount" in exc.value.missing_fields
        assert "VENDOR-ACME" not in str(exc.value)
        assert "5000" not in str(exc.value)
        assert "2500" not in str(exc.value)

    def test_risk_facts_fill_enrichment(self) -> None:
        enriched = require_enrich_execute_parameters(
            process_id=str(uuid4()),
            process_type="PROCUREMENT",
            process_name="Test",
            metadata_json={
                "process_json": {
                    "analytics": {
                        "risk_facts": {
                            "purchase_amount": "1500",
                            "vendor_id": "V-001",
                            "currency": "LKR",
                            "cost_centre": "IT-OPS",
                        }
                    }
                }
            },
            parameters={},
        )
        assert "tool_name" not in enriched or enriched.get("tool_name") != "__full_task_suite__"
        assert enriched["vendor_id"] == "V-001"
        assert enriched["amount"] == 1500.0
        assert enriched["currency"] == "LKR"
        assert enriched["cost_centre"] == "IT-OPS"


class TestG5ThreeWayInvoiceMatch:
    def test_three_way_match_with_policy_tolerance(self) -> None:
        po = ExpectedPurchase(
            po_reference="po-100",
            amount=Decimal("1000.00"),
            currency="lkr",
            vendor="acme",
        )
        receipt = ReceiptEvidence(
            amount=Decimal("1000.00"),
            po_reference="po-100",
            vendor="acme",
            receipt_status="SUCCESS",
        )
        invoice = InvoiceEvidence(
            amount=Decimal("1000.40"),
            po_reference="po-100",
            vendor="acme",
            currency="lkr",
        )
        within = three_way_match(
            po=po,
            receipt=receipt,
            invoice=invoice,
            amount_tolerance=Decimal("0.50"),
        )
        assert within.status == "MATCHED"

        outside = three_way_match(
            po=po,
            receipt=receipt,
            invoice=invoice,
            amount_tolerance=Decimal("0.01"),
        )
        assert outside.status == "MISMATCH"
        assert outside.mismatches


class TestG5ApprovalBranching:
    @pytest.mark.asyncio
    async def test_reject_moves_to_exception(self) -> None:
        from app.agents.agent4_orchestrator.exception_repository import InMemoryExceptionRepository
        from app.agents.agent4_orchestrator.exception_service import ExceptionService
        from app.agents.agent4_orchestrator.workflow import Agent4Workflow

        orchestrator = OrchestratorService()
        approvals = ApprovalService(orchestrator, InMemoryApprovalRepository())
        workflow = Agent4Workflow(
            orchestrator=orchestrator,
            approval_service=approvals,
            exception_service=ExceptionService(orchestrator, InMemoryExceptionRepository()),
            policy_retrieval=PolicyRetrievalService(InMemoryPolicyRepository()),
        )
        process_id = uuid4()
        await orchestrator.create_process(process_id, initial_stage=WorkflowStage.RISK_REVIEW)
        gate = await approvals.apply_risk_assessment(
            process_id,
            RiskAnalysisEngine().evaluate(
                RiskEvaluationContext(purchase_amount=Decimal("999999"))
            ),
        )
        assert gate.approval is not None
        decided = await approvals.reject_request(
            gate.approval.id,
            approver_id=uuid4(),
            comments="denied",
        )
        outcome = await workflow.apply_approval_outcome(process_id, decided.approval)
        assert outcome.current_stage is WorkflowStage.EXCEPTION
        assert outcome.eligible_for_execution is False
