"""Phase 10: process monitoring, KPIs, bottlenecks, and TO-BE recommendations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.agents.agent2_execution.tools.kpi_tools import calculate_kpi
from app.agents.agent2_execution.tools.schemas import CalculateKPIInput
from app.agents.agent4_orchestrator import OrchestratorService, WorkflowStage
from app.agents.agent4_orchestrator.state_machine import TransitionContext
from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID
from app.main import app
from app.monitoring.analytics import step_duration
from app.monitoring.demo import (
    PROCESS_0098,
    PROCESS_0105,
    STEP_APPROVAL,
    T0,
    seed_procurement_demo,
)
from app.monitoring.records import MonitoringProcess, MonitoringStep
from app.monitoring.recommendations import TobeRecommendationService
from app.monitoring.service import MonitoringService
from app.monitoring.store import get_monitoring_store
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
from app.tests.auth_helpers import override_current_user

OTHER_TENANT = UUID("00000000-0000-0000-0000-00000000d099")


@pytest.fixture
def seeded():
    seed_procurement_demo()
    return MonitoringService()


def _client(*, role: str = "requester", tenant_id: UUID = BPMFLOW_DEMO_TENANT_ID) -> TestClient:
    override_current_user(role=role, tenant_id=tenant_id)
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_timeline_reconstruction(seeded: MonitoringService):
    events = seeded.timeline(BPMFLOW_DEMO_TENANT_ID, PROCESS_0098)
    types = [item.event_type for item in events]
    assert "process_created" in types
    assert "discovery_started" in types
    assert "discovery_completed" in types
    assert "resource_allocation" in types
    assert "risk_review" in types
    assert "human_approval_requested" in types
    assert "human_approval_completed" in types
    assert "workflow_step_started" in types
    assert "workflow_step_completed" in types
    assert "invoice_matching_started" in types
    assert "invoice_matching_completed" in types
    assert "process_completed" in types
    assert all(item.process_id == PROCESS_0098 for item in events)
    assert all(item.timestamp.tzinfo is not None for item in events)
    stamps = [item.timestamp for item in events]
    assert stamps == sorted(stamps)


def test_step_duration_calculation(seeded: MonitoringService):
    steps = {item.workflow_step_id: item for item in seeded.step_durations(BPMFLOW_DEMO_TENANT_ID, PROCESS_0098)}
    approval = steps[STEP_APPROVAL]
    assert approval.start_time is not None
    assert approval.end_time is not None
    assert approval.duration_seconds == Decimal("7500.0000")
    assert approval.duration_minutes == Decimal("125.0000")
    assert approval.human_wait_seconds == Decimal("7200.0000")
    quote = next(item for item in steps.values() if item.name == "Quotation validation")
    assert quote.duration_seconds == Decimal("1800.0000")
    assert quote.human_wait_seconds is None


def test_missing_timestamp_is_unknown(seeded: MonitoringService):
    process = seeded.require_process(BPMFLOW_DEMO_TENANT_ID, PROCESS_0098)
    incomplete = MonitoringStep(
        workflow_step_id=uuid4(),
        name="Partial step",
        step_type="SYSTEM_ACTION",
        status="COMPLETED",
        started_at=T0,
        ended_at=None,
    )
    measured = step_duration(incomplete)
    assert measured.duration_seconds is None
    assert measured.duration_minutes is None
    assert process.completed_at is not None


def test_human_waiting_time_distinct_from_execution(seeded: MonitoringService):
    approval = next(
        item
        for item in seeded.step_durations(BPMFLOW_DEMO_TENANT_ID, PROCESS_0098)
        if item.workflow_step_id == STEP_APPROVAL
    )
    assert approval.human_wait_seconds == Decimal("7200.0000")
    assert approval.duration_seconds != approval.human_wait_seconds
    kpis = seeded.kpis(BPMFLOW_DEMO_TENANT_ID, process_id=PROCESS_0098)
    assert kpis.average_human_wait_time_seconds == Decimal("7200.0000")


def test_completion_and_exception_rates(seeded: MonitoringService):
    kpis = seeded.kpis(BPMFLOW_DEMO_TENANT_ID)
    assert kpis.total_processes == 2
    assert kpis.completed_processes == 1
    assert kpis.exception_processes == 1
    assert kpis.completion_rate == Decimal("0.5000")
    assert kpis.exception_rate == Decimal("0.5000")
    assert kpis.average_completion_time_seconds == Decimal("28800.0000")
    assert kpis.average_step_duration_seconds is not None
    assert kpis.total_exceptions == 2
    assert kpis.exceptions_by_code["BUDGET_EXCEEDED"] == 1
    assert kpis.exceptions_by_code["SOD_VIOLATION"] == 1


def test_exception_analytics_and_by_code(seeded: MonitoringService):
    analytics = seeded.exception_analytics(BPMFLOW_DEMO_TENANT_ID, PROCESS_0105)
    assert analytics.total_exceptions == 2
    assert analytics.open_exceptions == 2
    assert analytics.resolved_exceptions == 0
    assert analytics.exceptions_by_code["BUDGET_EXCEEDED"] == 1
    assert analytics.exceptions_by_workflow_step
    assert analytics.most_frequent_exception in {"BUDGET_EXCEEDED", "SOD_VIOLATION"}
    report = seeded.report(BPMFLOW_DEMO_TENANT_ID, PROCESS_0105)
    assert report.completed_at is None
    assert report.duration_seconds is None
    assert report.state == "EXCEPTION"


def test_bottleneck_ranking(seeded: MonitoringService):
    ranked = seeded.bottlenecks(BPMFLOW_DEMO_TENANT_ID, PROCESS_0098)
    assert ranked
    top = ranked[0]
    assert top.step == "Finance Approval"
    assert "highest_average_wait_time" in top.reason
    assert "highest_average_duration" in top.reason


def test_kpi_deterministic_and_time_filter(seeded: MonitoringService):
    first = seeded.kpis(BPMFLOW_DEMO_TENANT_ID)
    second = seeded.kpis(BPMFLOW_DEMO_TENANT_ID)
    assert first.model_dump() == second.model_dump()
    inside = seeded.kpis(
        BPMFLOW_DEMO_TENANT_ID,
        window_start=T0 - timedelta(minutes=1),
        window_end=T0 + timedelta(days=2),
    )
    assert inside.total_processes == 2
    outside = seeded.kpis(
        BPMFLOW_DEMO_TENANT_ID,
        window_start=datetime(2025, 1, 1, tzinfo=UTC),
        window_end=datetime(2025, 2, 1, tzinfo=UTC),
    )
    assert outside.total_processes == 0
    assert outside.insufficient_evidence is True
    assert outside.completion_rate is None


@pytest.mark.asyncio
async def test_calculate_kpi_returns_real_values(seeded: MonitoringService):
    out = await calculate_kpi(
        session=None,
        input_data=CalculateKPIInput(
            process_type="procurement",
            days_back=30,
            tenant_id=str(BPMFLOW_DEMO_TENANT_ID),
            process_id=str(PROCESS_0098),
        ),
    )
    assert out.avg_cycle_time_hours == 8.0
    assert out.completion_rate == 1.0
    assert out.throughput == 1
    assert out.bottleneck_task == "Finance Approval"
    assert out.sla_compliance_rate == 0.0


@pytest.mark.asyncio
async def test_monitoring_does_not_modify_process_state(seeded: MonitoringService):
    orchestrator = OrchestratorService()
    process_id = uuid4()
    await orchestrator.create_process(process_id, initial_stage=WorkflowStage.WORKFLOW_EXECUTION)
    before = await orchestrator.get_current_stage(process_id)
    seeded.report(BPMFLOW_DEMO_TENANT_ID, PROCESS_0098)
    await calculate_kpi(
        None,
        CalculateKPIInput(tenant_id=str(BPMFLOW_DEMO_TENANT_ID), process_id=str(PROCESS_0098)),
    )
    after = await orchestrator.get_current_stage(process_id)
    assert before is WorkflowStage.WORKFLOW_EXECUTION
    assert after is before
    demo = seeded.require_process(BPMFLOW_DEMO_TENANT_ID, PROCESS_0098)
    assert demo.current_stage == "COMPLETED"


@pytest.mark.asyncio
async def test_agent4_still_owns_state_transitions(seeded: MonitoringService):
    orchestrator = OrchestratorService()
    process_id = uuid4()
    await orchestrator.create_process(process_id, initial_stage=WorkflowStage.INVOICE_MATCHING)
    seeded.kpis(BPMFLOW_DEMO_TENANT_ID, process_id=PROCESS_0098)
    await orchestrator.move_process(
        process_id,
        WorkflowStage.COMPLETED,
        reason="invoice matched",
        transition_context=TransitionContext(invoice_match_status="MATCHED"),
    )
    assert await orchestrator.get_current_stage(process_id) is WorkflowStage.COMPLETED


@pytest.mark.asyncio
async def test_recommendations_evidence_idempotency_and_no_activation(seeded: MonitoringService):
    service = TobeRecommendationService()
    first = await service.generate(BPMFLOW_DEMO_TENANT_ID, PROCESS_0098)
    second = await service.generate(BPMFLOW_DEMO_TENANT_ID, PROCESS_0098)
    assert first
    assert {item.id for item in first} == {item.id for item in second}
    parallel = next(item for item in first if item.recommendation_type == "parallelize_independent_steps")
    assert parallel.evidence
    assert parallel.activates_workflow is False
    assert all(item.source for item in parallel.evidence)
    reviewed = service.review(
        BPMFLOW_DEMO_TENANT_ID,
        parallel.id,
        decision="ACCEPTED",
        reviewer_id=uuid4(),
        role="approver",
    )
    assert reviewed.status == "ACCEPTED"
    assert reviewed.activates_workflow is False
    still = seeded.require_process(BPMFLOW_DEMO_TENANT_ID, PROCESS_0098)
    assert still.current_stage == "COMPLETED"


@pytest.mark.asyncio
async def test_policy_conflicting_recommendation_rejected(seeded: MonitoringService):
    repo = InMemoryPolicyRepository()
    ingestion = PolicyIngestionService(repo)
    await ingestion.ingest(
        tenant_id=BPMFLOW_DEMO_TENANT_ID,
        uploaded_by=uuid4(),
        request=PolicyCreateRequest(
            name="Procurement Policy",
            category=PolicyCategory.PROCUREMENT,
            version_label="2026.1",
            activate=True,
            text_content="Approvals and SoD are mandatory.",
            rules=[
                PolicyRule(
                    rule_type=PolicyRuleType.APPROVAL_THRESHOLD,
                    operator=PolicyOperator.GT,
                    threshold_value=Decimal("1000000"),
                ),
                PolicyRule(rule_type=PolicyRuleType.SEGREGATION_OF_DUTIES),
                PolicyRule(rule_type=PolicyRuleType.BUDGET_LIMIT, threshold_value=Decimal("2000000")),
                PolicyRule(rule_type=PolicyRuleType.REQUIRED_EVIDENCE, required_evidence=["quotation"]),
            ],
        ),
    )
    service = TobeRecommendationService(policy_retrieval=PolicyRetrievalService(repo))
    items = await service.generate(
        BPMFLOW_DEMO_TENANT_ID, PROCESS_0098, include_forbidden="remove_mandatory_approval"
    )
    blocked = next(item for item in items if item.recommendation_type == "remove_mandatory_approval")
    assert blocked.status == "NOT_ALLOWED"
    assert blocked.policy_status == "NOT_ALLOWED"
    assert blocked.activates_workflow is False


def test_recommendation_review_authorization(seeded: MonitoringService):
    client = _client(role="requester")
    gen = client.post(f"/api/v1/processes/{PROCESS_0098}/recommendations/generate")
    assert gen.status_code == 200
    rec_id = gen.json()[0]["id"]
    denied = client.post(
        f"/api/v1/recommendations/{rec_id}/review",
        json={"decision": "ACCEPTED"},
    )
    assert denied.status_code == 403
    approver = _client(role="approver")
    allowed = approver.post(
        f"/api/v1/recommendations/{rec_id}/review",
        json={"decision": "ACCEPTED"},
    )
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["status"] == "ACCEPTED"
    assert body["activates_workflow"] is False


def test_tenant_isolation_and_cross_tenant_denied(seeded: MonitoringService):
    other_process = MonitoringProcess(
        process_id=uuid4(),
        tenant_id=OTHER_TENANT,
        name="secret",
        current_stage="COMPLETED",
        status="COMPLETED",
        created_at=T0,
        completed_at=T0 + timedelta(hours=1),
    )
    get_monitoring_store().upsert_process(other_process)
    client_a = _client(tenant_id=BPMFLOW_DEMO_TENANT_ID)
    missing = client_a.get(f"/api/v1/processes/{other_process.process_id}/kpis")
    assert missing.status_code == 404
    client_b = _client(tenant_id=OTHER_TENANT)
    ok = client_b.get(f"/api/v1/processes/{other_process.process_id}/monitoring")
    assert ok.status_code == 200
    rec_client = _client(tenant_id=BPMFLOW_DEMO_TENANT_ID)
    rec_client.post(f"/api/v1/processes/{PROCESS_0098}/recommendations/generate")
    rec_id = rec_client.get(f"/api/v1/processes/{PROCESS_0098}/recommendations").json()[0]["id"]
    other_user = _client(tenant_id=OTHER_TENANT)
    leaked_kpi = other_user.get(f"/api/v1/processes/{PROCESS_0098}/kpis")
    assert leaked_kpi.status_code == 404
    leaked_rec = other_user.get(f"/api/v1/recommendations/{rec_id}")
    assert leaked_rec.status_code == 403


def test_pr_0098_and_0105_monitoring_api(seeded: MonitoringService):
    client = _client()
    report = client.get(f"/api/v1/processes/{PROCESS_0098}/monitoring")
    assert report.status_code == 200
    body = report.json()
    assert body["state"] == "COMPLETED"
    assert body["completed_at"] is not None
    assert any(event["event_type"] == "process_completed" for event in body["timeline"])
    blocked = client.get(f"/api/v1/processes/{PROCESS_0105}/monitoring")
    assert blocked.status_code == 200
    failed = blocked.json()
    assert failed["state"] == "EXCEPTION"
    assert failed["completed_at"] is None
    codes = {item["code"] for item in failed["exceptions"]}
    assert "BUDGET_EXCEEDED" in codes
    assert "SOD_VIOLATION" in codes


def test_no_invented_kpi_values():
    empty = MonitoringService().kpis(BPMFLOW_DEMO_TENANT_ID)
    assert empty.insufficient_evidence is True
    assert empty.completion_rate is None
    assert empty.average_completion_time_seconds is None
    assert empty.bottleneck_steps == []
