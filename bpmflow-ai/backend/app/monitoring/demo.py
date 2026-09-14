"""Demo procurement monitoring facts for PR-2026-0098 and PR-2026-0105."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.agents.agent4_orchestrator.constants import ExceptionStatus, ExceptionType, WorkflowStage
from app.agents.agent4_orchestrator.workflow_plan.constants import WorkflowStepStatus, WorkflowStepType
from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID
from app.monitoring.records import (
    MonitoringApproval,
    MonitoringEvent,
    MonitoringException,
    MonitoringProcess,
    MonitoringStep,
)
from app.monitoring.store import get_monitoring_store

PROCESS_0098 = UUID("10000000-0000-4000-8000-000000000098")
PROCESS_0105 = UUID("10000000-0000-4000-8000-000000000105")
PLAN_0098 = UUID("20000000-0000-4000-8000-000000000098")
PLAN_0105 = UUID("20000000-0000-4000-8000-000000000105")
STEP_QUOTE = UUID("30000000-0000-4000-8000-000000000001")
STEP_DOC = UUID("30000000-0000-4000-8000-000000000002")
STEP_APPROVAL = UUID("30000000-0000-4000-8000-000000000003")
STEP_PO = UUID("30000000-0000-4000-8000-000000000004")
STEP_INVOICE = UUID("30000000-0000-4000-8000-000000000005")
STEP_BUDGET = UUID("30000000-0000-4000-8000-000000000006")
APPROVAL_0098 = UUID("40000000-0000-4000-8000-000000000098")
EXC_BUDGET = UUID("50000000-0000-4000-8000-000000000105")
EXC_SOD = UUID("50000000-0000-4000-8000-000000000106")
T0 = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


def seed_procurement_demo(*, tenant_id: UUID = BPMFLOW_DEMO_TENANT_ID) -> None:
    store = get_monitoring_store()
    store.upsert_process(_pr_0098(tenant_id))
    store.upsert_process(_pr_0105(tenant_id))


def _pr_0098(tenant_id: UUID) -> MonitoringProcess:
    return MonitoringProcess(
        process_id=PROCESS_0098,
        tenant_id=tenant_id,
        name="PR-2026-0098",
        current_stage=WorkflowStage.COMPLETED.value,
        status="COMPLETED",
        created_at=T0,
        completed_at=T0 + timedelta(hours=8),
        trace_id="trace-pr-2026-0098",
        workflow_plan_id=PLAN_0098,
        purchase_request_id="PR-2026-0098",
        events=[
            MonitoringEvent("discovery_started", T0 + timedelta(minutes=5), actor="agent1_discovery"),
            MonitoringEvent("discovery_completed", T0 + timedelta(minutes=20), actor="agent1_discovery", status="COMPLETE"),
            MonitoringEvent("resource_allocation", T0 + timedelta(minutes=25), actor="agent3_resources"),
            MonitoringEvent("risk_review", T0 + timedelta(minutes=30), actor="agent4_orchestrator"),
        ],
        approvals=[
            MonitoringApproval(
                approval_id=APPROVAL_0098,
                status="APPROVED",
                requested_at=T0 + timedelta(hours=1),
                decided_at=T0 + timedelta(hours=3),
                workflow_step_id=STEP_APPROVAL,
            )
        ],
        steps=[
            MonitoringStep(
                workflow_step_id=STEP_QUOTE,
                name="Quotation validation",
                step_type=WorkflowStepType.VALIDATION.value,
                status=WorkflowStepStatus.COMPLETED.value,
                started_at=T0 + timedelta(minutes=40),
                ended_at=T0 + timedelta(minutes=70),
                step_key="quotation_validation",
            ),
            MonitoringStep(
                workflow_step_id=STEP_DOC,
                name="Document review",
                step_type=WorkflowStepType.DOCUMENT_REVIEW.value,
                status=WorkflowStepStatus.COMPLETED.value,
                started_at=T0 + timedelta(minutes=40),
                ended_at=T0 + timedelta(minutes=55),
                step_key="document_review",
            ),
            MonitoringStep(
                workflow_step_id=STEP_APPROVAL,
                name="Finance Approval",
                step_type=WorkflowStepType.APPROVAL.value,
                status=WorkflowStepStatus.COMPLETED.value,
                started_at=T0 + timedelta(hours=1),
                ended_at=T0 + timedelta(hours=3, minutes=5),
                waiting_started_at=T0 + timedelta(hours=1),
                waiting_ended_at=T0 + timedelta(hours=3),
                approval_required=True,
                depends_on_step_keys=["quotation_validation"],
                step_key="finance_approval",
            ),
            MonitoringStep(
                workflow_step_id=STEP_PO,
                name="Create purchase order",
                step_type=WorkflowStepType.SYSTEM_ACTION.value,
                status=WorkflowStepStatus.COMPLETED.value,
                started_at=T0 + timedelta(hours=3, minutes=10),
                ended_at=T0 + timedelta(hours=3, minutes=20),
                depends_on_step_keys=["finance_approval"],
                step_key="create_po",
            ),
            MonitoringStep(
                workflow_step_id=STEP_INVOICE,
                name="Invoice matching",
                step_type=WorkflowStepType.VALIDATION.value,
                status=WorkflowStepStatus.COMPLETED.value,
                started_at=T0 + timedelta(hours=7),
                ended_at=T0 + timedelta(hours=7, minutes=15),
                depends_on_step_keys=["create_po"],
                step_key="invoice_matching",
            ),
        ],
    )


def _pr_0105(tenant_id: UUID) -> MonitoringProcess:
    return MonitoringProcess(
        process_id=PROCESS_0105,
        tenant_id=tenant_id,
        name="PR-2026-0105",
        current_stage=WorkflowStage.EXCEPTION.value,
        status="EXCEPTION",
        created_at=T0 + timedelta(days=1),
        completed_at=None,
        trace_id="trace-pr-2026-0105",
        workflow_plan_id=PLAN_0105,
        purchase_request_id="PR-2026-0105",
        events=[
            MonitoringEvent("discovery_started", T0 + timedelta(days=1, minutes=5), actor="agent1_discovery"),
            MonitoringEvent("discovery_completed", T0 + timedelta(days=1, minutes=15), actor="agent1_discovery"),
            MonitoringEvent("risk_review", T0 + timedelta(days=1, minutes=20), actor="agent4_orchestrator"),
        ],
        steps=[
            MonitoringStep(
                workflow_step_id=STEP_BUDGET,
                name="Budget and SoD check",
                step_type=WorkflowStepType.VALIDATION.value,
                status=WorkflowStepStatus.FAILED.value,
                started_at=T0 + timedelta(days=1, minutes=25),
                ended_at=T0 + timedelta(days=1, minutes=28),
                failure_count=1,
                exception_count=2,
                step_key="budget_sod_check",
            )
        ],
        exceptions=[
            MonitoringException(
                exception_id=EXC_BUDGET,
                code=ExceptionType.BUDGET_EXCEEDED.value,
                status=ExceptionStatus.OPEN.value,
                created_at=T0 + timedelta(days=1, minutes=28),
                workflow_step_id=STEP_BUDGET,
                title="Budget exceeded",
            ),
            MonitoringException(
                exception_id=EXC_SOD,
                code=ExceptionType.SOD_VIOLATION.value,
                status=ExceptionStatus.OPEN.value,
                created_at=T0 + timedelta(days=1, minutes=28),
                workflow_step_id=STEP_BUDGET,
                title="SoD violation",
            ),
        ],
    )
