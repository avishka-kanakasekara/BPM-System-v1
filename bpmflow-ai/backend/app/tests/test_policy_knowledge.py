"""Tests for Company Policy & Knowledge Repository + Agent 4 policy-aware risk."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents.agent4_orchestrator import (
    Agent4Workflow,
    ApprovalService,
    InMemoryApprovalRepository,
    OrchestratorService,
    RiskAnalysisEngine,
    RiskEvaluationContext,
    RiskType,
    WorkflowStage,
)
from app.agents.agent4_orchestrator.constants import RiskRecommendation
from app.policy_knowledge import (
    PolicyCategory,
    PolicyCreateRequest,
    PolicyIngestionService,
    PolicyRetrievalService,
    PolicyRetrievalStatus,
    PolicyRule,
    PolicyRuleType,
    PolicyVersionStatus,
    reset_default_policy_repository,
)
from app.policy_knowledge.constants import PolicyOperator
from app.policy_knowledge.repository import InMemoryPolicyRepository
from app.policy_knowledge.schemas import PolicyRiskSnapshot


@pytest.fixture
def repo() -> InMemoryPolicyRepository:
    return InMemoryPolicyRepository()


@pytest.fixture
def ingestion(repo: InMemoryPolicyRepository) -> PolicyIngestionService:
    return PolicyIngestionService(repo)


@pytest.fixture
def retrieval(repo: InMemoryPolicyRepository) -> PolicyRetrievalService:
    return PolicyRetrievalService(repo)


async def _seed_procurement_policy(
    ingestion: PolicyIngestionService,
    *,
    tenant_id,
    version: str = "2026.1",
    threshold: str = "1000000",
    currency: str = "LKR",
    activate: bool = True,
    name: str = "Procurement Policy",
):
    return await ingestion.ingest(
        tenant_id=tenant_id,
        uploaded_by=uuid4(),
        request=PolicyCreateRequest(
            name=name,
            category=PolicyCategory.PROCUREMENT,
            version_label=version,
            activate=activate,
            text_content=(
                f"Approval Limits\n\n"
                f"Purchases above {threshold} {currency} require Senior Management approval.\n"
                f"A quotation is required for procurement requests.\n"
                f"Segregation of duties: requester cannot approve."
            ),
            rules=[
                PolicyRule(
                    rule_type=PolicyRuleType.APPROVAL_THRESHOLD,
                    operator=PolicyOperator.GT,
                    threshold_value=Decimal(threshold),
                    currency=currency,
                    required_approval="SENIOR_MANAGEMENT",
                    description=f"Purchases above {threshold} {currency}",
                ),
                PolicyRule(
                    rule_type=PolicyRuleType.REQUIRED_EVIDENCE,
                    required_evidence=["quotation"],
                ),
                PolicyRule(
                    rule_type=PolicyRuleType.SEGREGATION_OF_DUTIES,
                    description="Requester cannot approve",
                ),
            ],
        ),
    )


@pytest.mark.asyncio
class TestPolicyRepositoryBasics:
    async def test_active_policy_retrieval(self, ingestion, retrieval) -> None:
        tenant = uuid4()
        await _seed_procurement_policy(ingestion, tenant_id=tenant)
        result = await retrieval.search(
            tenant_id=tenant,
            query="procurement approval threshold for purchase amount",
            categories=[PolicyCategory.PROCUREMENT],
        )
        assert result.status is PolicyRetrievalStatus.FOUND
        assert result.version == "2026.1"
        assert any(r.threshold_value == Decimal("1000000") for r in result.rules)

    async def test_archived_policy_ignored(self, ingestion, retrieval, repo) -> None:
        tenant = uuid4()
        policy = await _seed_procurement_policy(
            ingestion, tenant_id=tenant, version="2025.1", threshold="500000"
        )
        version_id = policy.versions[0].id
        await repo.archive_version(tenant, policy.id, version_id)
        await _seed_procurement_policy(
            ingestion, tenant_id=tenant, version="2026.1", threshold="1000000"
        )
        snapshot = await retrieval.build_risk_snapshot(
            tenant_id=tenant, purchase_amount=Decimal("1500000")
        )
        assert snapshot.approval_threshold == Decimal("1000000")
        assert "2025.1" not in snapshot.policy_versions

    async def test_tenant_isolation(self, ingestion, retrieval) -> None:
        tenant_a = uuid4()
        tenant_b = uuid4()
        await _seed_procurement_policy(ingestion, tenant_id=tenant_a)
        result = await retrieval.search(
            tenant_id=tenant_b,
            query="procurement approval threshold",
        )
        assert result.status is PolicyRetrievalStatus.NOT_FOUND

    async def test_category_filtering(self, ingestion, retrieval) -> None:
        tenant = uuid4()
        await _seed_procurement_policy(ingestion, tenant_id=tenant)
        result = await retrieval.search(
            tenant_id=tenant,
            query="procurement",
            categories=[PolicyCategory.SECURITY],
        )
        assert result.status is PolicyRetrievalStatus.NOT_FOUND

    async def test_version_selection_activates_one(self, ingestion, repo) -> None:
        tenant = uuid4()
        first = await _seed_procurement_policy(
            ingestion, tenant_id=tenant, version="2025.1", activate=True
        )
        second = await _seed_procurement_policy(
            ingestion, tenant_id=tenant, version="2026.1", activate=True
        )
        assert first.id == second.id
        refreshed = await repo.get_policy(tenant, second.id)
        assert refreshed is not None
        statuses = {v.version_label: v.status for v in refreshed.versions}
        assert statuses["2025.1"] is PolicyVersionStatus.ARCHIVED
        assert statuses["2026.1"] is PolicyVersionStatus.ACTIVE

    async def test_policy_not_found(self, retrieval) -> None:
        result = await retrieval.search(tenant_id=uuid4(), query="threshold")
        assert result.status is PolicyRetrievalStatus.NOT_FOUND

    async def test_insufficient_policy_evidence(self, ingestion, retrieval) -> None:
        tenant = uuid4()
        await ingestion.ingest(
            tenant_id=tenant,
            uploaded_by=uuid4(),
            request=PolicyCreateRequest(
                name="Vague Policy",
                category=PolicyCategory.GENERAL,
                version_label="1",
                activate=True,
                text_content="Be careful with spending.",
                rules=[],
            ),
        )
        snapshot = await retrieval.build_risk_snapshot(
            tenant_id=tenant, purchase_amount=Decimal("1500000")
        )
        assert snapshot.status in (
            PolicyRetrievalStatus.INSUFFICIENT_EVIDENCE,
            PolicyRetrievalStatus.FOUND,
        )
        if snapshot.high_value_threshold is None and snapshot.approval_threshold is None:
            assert snapshot.status is PolicyRetrievalStatus.INSUFFICIENT_EVIDENCE

    async def test_policy_conflict(self, ingestion, retrieval) -> None:
        tenant = uuid4()
        await _seed_procurement_policy(
            ingestion,
            tenant_id=tenant,
            version="A",
            threshold="1000000",
            name="Procurement Policy A",
        )
        # Second distinct policy identity with different threshold while both active
        await ingestion.ingest(
            tenant_id=tenant,
            uploaded_by=uuid4(),
            request=PolicyCreateRequest(
                name="Procurement Policy B",
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
        result = await retrieval.search(
            tenant_id=tenant,
            query="procurement approval threshold",
            categories=[PolicyCategory.PROCUREMENT],
        )
        assert result.status is PolicyRetrievalStatus.CONFLICT


class TestPolicyAwareRiskRules:
    def test_high_value_from_policy_threshold(self) -> None:
        snapshot = PolicyRiskSnapshot(
            status=PolicyRetrievalStatus.FOUND,
            query="q",
            high_value_threshold=Decimal("1000000"),
            approval_threshold=Decimal("1000000"),
            currency="LKR",
            policy_versions=["2026.1"],
            confidence=Decimal("0.9"),
        )
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                purchase_amount=Decimal("1500000"),
                currency="LKR",
                policy_snapshot=snapshot,
            )
        )
        types = {f.risk_type for f in assessment.findings}
        assert RiskType.HIGH_VALUE_PURCHASE in types
        assert RiskType.POLICY_UNCERTAINTY not in types
        finding = next(
            f for f in assessment.findings if f.risk_type is RiskType.HIGH_VALUE_PURCHASE
        )
        assert finding.threshold == Decimal("1000000")
        assert finding.amount == Decimal("1500000")

    def test_no_invented_threshold_when_policy_missing(self) -> None:
        snapshot = PolicyRiskSnapshot(
            status=PolicyRetrievalStatus.NOT_FOUND,
            query="q",
            confidence=Decimal("0"),
        )
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                purchase_amount=Decimal("1500000"),
                # Legacy default would be 10000 — must NOT be used in policy mode.
                policy_snapshot=snapshot,
            )
        )
        types = {f.risk_type for f in assessment.findings}
        assert RiskType.POLICY_UNCERTAINTY in types
        assert RiskType.HIGH_VALUE_PURCHASE not in types

    def test_budget_exceeded(self) -> None:
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                purchase_amount=Decimal("1500000"),
                available_budget=Decimal("1000000"),
            )
        )
        assert RiskType.BUDGET_VALIDATION_FAILURE in {
            f.risk_type for f in assessment.findings
        }

    def test_missing_required_evidence_from_policy(self) -> None:
        snapshot = PolicyRiskSnapshot(
            status=PolicyRetrievalStatus.FOUND,
            query="q",
            high_value_threshold=Decimal("1000000"),
            required_evidence=["quotation"],
            policy_versions=["2026.1"],
        )
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                purchase_amount=Decimal("100"),
                provided_evidence=[],
                policy_snapshot=snapshot,
            )
        )
        assert RiskType.MISSING_EVIDENCE in {f.risk_type for f in assessment.findings}

    def test_unauthorized_role(self) -> None:
        snapshot = PolicyRiskSnapshot(
            status=PolicyRetrievalStatus.FOUND,
            query="q",
            high_value_threshold=Decimal("1000000"),
            required_roles=["SENIOR_MANAGEMENT"],
            policy_versions=["2026.1"],
        )
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                purchase_amount=Decimal("100"),
                requester_roles=["REQUESTER"],
                policy_snapshot=snapshot,
            )
        )
        finding = next(
            f for f in assessment.findings if f.risk_type is RiskType.UNAUTHORIZED_ACTION
        )
        assert finding.recommendation is RiskRecommendation.BLOCK_ACTION

    def test_sla_risk(self) -> None:
        snapshot = PolicyRiskSnapshot(
            status=PolicyRetrievalStatus.FOUND,
            query="q",
            high_value_threshold=Decimal("1000000"),
            sla_hours=Decimal("24"),
            policy_versions=["2026.1"],
        )
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                purchase_amount=Decimal("100"),
                process_age_hours=Decimal("48"),
                policy_snapshot=snapshot,
            )
        )
        assert RiskType.SLA_RISK in {f.risk_type for f in assessment.findings}

    def test_policy_conflict_finding(self) -> None:
        snapshot = PolicyRiskSnapshot(
            status=PolicyRetrievalStatus.CONFLICT,
            query="q",
            message="conflicting thresholds",
            policy_versions=["A", "B"],
        )
        assessment = RiskAnalysisEngine().evaluate(
            RiskEvaluationContext(
                purchase_amount=Decimal("1500000"),
                policy_snapshot=snapshot,
            )
        )
        assert RiskType.POLICY_CONFLICT in {f.risk_type for f in assessment.findings}


@pytest.mark.asyncio
class TestWorkflowPolicyIntegration:
    async def test_policy_threshold_requires_human_approval(
        self, ingestion, retrieval
    ) -> None:
        tenant = uuid4()
        await _seed_procurement_policy(ingestion, tenant_id=tenant)
        orchestrator = OrchestratorService()
        approvals = ApprovalService(orchestrator, InMemoryApprovalRepository())
        workflow = Agent4Workflow(
            orchestrator=orchestrator,
            approval_service=approvals,
            policy_retrieval=retrieval,
        )
        process_id = uuid4()
        await orchestrator.create_process(
            process_id, initial_stage=WorkflowStage.RISK_REVIEW
        )
        result = await workflow.handle_risk(
            process_id,
            RiskEvaluationContext(purchase_amount=Decimal("1500000"), currency="LKR"),
            tenant_id=tenant,
        )
        assert result.human_approval_required is True
        assert result.current_stage is WorkflowStage.AWAITING_HUMAN_APPROVAL
        assert result.policy_decision is not None
        assert result.policy_decision.approval_required is True
        types = {f.risk_type for f in (result.risk_assessment.findings if result.risk_assessment else [])}
        assert RiskType.HIGH_VALUE_PURCHASE in types

    async def test_legacy_path_without_tenant_still_works(self) -> None:
        orchestrator = OrchestratorService()
        approvals = ApprovalService(orchestrator, InMemoryApprovalRepository())
        workflow = Agent4Workflow(
            orchestrator=orchestrator,
            approval_service=approvals,
            policy_retrieval=PolicyRetrievalService(InMemoryPolicyRepository()),
        )
        process_id = uuid4()
        await orchestrator.create_process(
            process_id, initial_stage=WorkflowStage.RISK_REVIEW
        )
        # No tenant_id => legacy threshold path (10000)
        result = await workflow.handle_risk(
            process_id,
            RiskEvaluationContext(purchase_amount=Decimal("25000")),
        )
        assert result.human_approval_required is True


def test_reset_default_repo_isolation() -> None:
    reset_default_policy_repository()
    repo = reset_default_policy_repository()
    assert isinstance(repo, InMemoryPolicyRepository)
