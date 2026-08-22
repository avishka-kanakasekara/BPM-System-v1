"""
Agent 2 — Schema Validation Tests

Tests instantiation, JSON round-tripping, and validation errors for all Pydantic v2 schemas:
- AgentMessage
- ExecutionPlan
- AgentDecision
- ToolCallContract & ToolResultContract
- FailureDiagnosis
- RecoveryDecision
- ExecutionReceipt
- KPIResult
- SLAAnalysis
- OptimizationRecommendationSchema
- EmailRequest & EmailResult
"""

import pytest
from pydantic import ValidationError

from app.communication.schemas import EmailRequest, EmailResult
from app.llm.schemas import (
    AgentDecision,
    AgentMessage,
    ExecutionPlan,
    ExecutionReceipt,
    FailureDiagnosis,
    KPIResult,
    OptimizationRecommendationSchema,
    RecoveryDecision,
    SLAAnalysis,
    ToolCallContract,
    ToolResultContract,
)


# ---------------------------------------------------------------------------
# Test Fixtures & Valid Instances
# ---------------------------------------------------------------------------

def test_agent_message_valid():
    msg = AgentMessage(
        message_id="msg-1001",
        process_id="proc-5001",
        trace_id="trace-abc",
        sender="agent_4",
        receiver="agent_2",
        task_type="EXECUTE_TASK",
        payload={"task_id": "task-77"},
        evidence_refs=["ref-1"],
        confidence=0.95,
        status="AUTHORIZED",
    )
    # Round-trip JSON test
    json_str = msg.model_dump_json()
    reconstructed = AgentMessage.model_validate_json(json_str)
    assert reconstructed == msg
    assert reconstructed.status == "AUTHORIZED"


def test_agent_message_invalid_status():
    with pytest.raises(ValidationError):
        AgentMessage(
            message_id="msg-1",
            process_id="proc-1",
            sender="agent_4",
            receiver="agent_2",
            task_type="TEST",
            status="UNKNOWN_STATUS",  # invalid status
        )


def test_execution_plan_valid():
    plan = ExecutionPlan(
        task_id="task-123",
        objective="Process purchase requisition for laptops",
        steps=["Validate request", "Request quotations", "Create PO draft"],
        selected_tools=["validate_request", "request_quotation", "create_po_draft"],
        reasoning_summary="Sequential execution of procurement workflow steps",
        risk_level="LOW",
        confidence=0.92,
        fallback_strategy="Escalate to procurement officer if quotation timeout occurs",
        requires_human=False,
    )
    json_str = plan.model_dump_json()
    reconstructed = ExecutionPlan.model_validate_json(json_str)
    assert reconstructed == plan
    assert reconstructed.risk_level == "LOW"


def test_execution_plan_invalid_risk_level():
    with pytest.raises(ValidationError):
        ExecutionPlan(
            task_id="task-123",
            objective="Obj",
            steps=["Step 1"],
            selected_tools=["tool_1"],
            reasoning_summary="Reasoning",
            risk_level="SUPER_HIGH",  # Invalid risk level
            confidence=0.9,
        )


def test_agent_decision_valid():
    decision = AgentDecision(
        decision="EXECUTE",
        confidence=0.88,
        selected_tool="send_role_email",
        reason="Assigned employee SLA is approaching 80%",
        parameters={"recipient_role": "assigned_employee", "template": "sla_warning"},
        risk_level="LOW",
        fallback_strategy="Log escalation warning",
        requires_human=False,
    )
    json_str = decision.model_dump_json()
    reconstructed = AgentDecision.model_validate_json(json_str)
    assert reconstructed == decision
    assert reconstructed.decision == "EXECUTE"


def test_agent_decision_invalid_decision():
    with pytest.raises(ValidationError):
        AgentDecision(
            decision="DO_NOTHING",  # Invalid decision literal
            confidence=0.5,
            reason="Unknown",
        )


def test_tool_call_and_result_valid():
    tool_call = ToolCallContract(
        name="create_po_draft",
        parameters={"vendor_id": "v-100", "amount": 4500.00},
    )
    call_json = tool_call.model_dump_json()
    assert ToolCallContract.model_validate_json(call_json) == tool_call

    tool_result = ToolResultContract(
        name="create_po_draft",
        result={"po_number": "PO-998811"},
        status="SUCCESS",
        latency_ms=145,
        error_message="",
    )
    res_json = tool_result.model_dump_json()
    assert ToolResultContract.model_validate_json(res_json) == tool_result


def test_tool_result_invalid_status():
    with pytest.raises(ValidationError):
        ToolResultContract(
            name="create_po_draft",
            status="CRASHED",  # Invalid status literal
        )


def test_failure_diagnosis_valid():
    diag = FailureDiagnosis(
        failure_type="TEMPORARY",
        confidence=0.9,
        reasoning="ERP connection timed out during socket handshake",
        recommended_action="Retry after 5 seconds using exponential backoff",
    )
    json_str = diag.model_dump_json()
    reconstructed = FailureDiagnosis.model_validate_json(json_str)
    assert reconstructed == diag
    assert reconstructed.failure_type == "TEMPORARY"


def test_failure_diagnosis_invalid_type():
    with pytest.raises(ValidationError):
        FailureDiagnosis(
            failure_type="FATAL_ERROR",  # Invalid failure_type
            confidence=0.5,
            reasoning="Reason",
            recommended_action="Action",
        )


def test_recovery_decision_valid():
    rec = RecoveryDecision(
        retry=True,
        delay_seconds=10,
        alternative_strategy="Use cached ERP session token",
        escalate=False,
        reasoning="Temporary network glitch identified",
    )
    json_str = rec.model_dump_json()
    reconstructed = RecoveryDecision.model_validate_json(json_str)
    assert reconstructed == rec
    assert reconstructed.retry is True


def test_execution_receipt_valid():
    receipt = ExecutionReceipt(
        id="rec-001",
        process_id="proc-100",
        task_id="task-200",
        agent_id="agent_2",
        tool_name="create_po_draft",
        action="CREATE_DRAFT",
        attempt_number=1,
        idempotency_key="proc-100-task-200-CREATE_DRAFT",
        started_at="2026-08-15T10:00:00Z",
        completed_at="2026-08-15T10:00:01Z",
        status="SUCCESS",
        result={"po_id": "po-55"},
        error_type="",
        error_message="",
        latency_ms=1050,
    )
    json_str = receipt.model_dump_json()
    reconstructed = ExecutionReceipt.model_validate_json(json_str)
    assert reconstructed == receipt
    assert reconstructed.idempotency_key == "proc-100-task-200-CREATE_DRAFT"


def test_execution_receipt_invalid_status():
    with pytest.raises(ValidationError):
        ExecutionReceipt(
            id="rec-001",
            process_id="p-1",
            task_id="t-1",
            agent_id="agent_2",
            tool_name="tool",
            action="act",
            idempotency_key="key",
            started_at="2026-08-15T10:00:00Z",
            status="PENDING_UNKNOWN",  # Invalid status
        )


def test_kpi_result_valid():
    kpi = KPIResult(
        process_type="procurement",
        time_window_start="2026-08-01T00:00:00Z",
        time_window_end="2026-08-15T00:00:00Z",
        avg_cycle_time_hours=36.5,
        avg_task_duration_hours=4.2,
        completion_rate=0.94,
        sla_compliance_rate=0.88,
        failure_rate=0.03,
        throughput=150,
        bottleneck_task="manager_approval",
        kpi_data={"total_cases": 160},
    )
    json_str = kpi.model_dump_json()
    reconstructed = KPIResult.model_validate_json(json_str)
    assert reconstructed == kpi
    assert reconstructed.throughput == 150


def test_sla_analysis_valid():
    sla = SLAAnalysis(
        predicted_breach_probability=0.75,
        elapsed_hours=18.0,
        sla_hours=24.0,
        historical_average_hours=12.0,
        is_breached=False,
        recommended_action="Send reminder email to assigned approver",
    )
    json_str = sla.model_dump_json()
    reconstructed = SLAAnalysis.model_validate_json(json_str)
    assert reconstructed == sla
    assert reconstructed.predicted_breach_probability == 0.75


def test_sla_analysis_invalid_confidence():
    with pytest.raises(ValidationError):
        SLAAnalysis(
            predicted_breach_probability=1.5,  # Out of bounds (> 1.0)
            elapsed_hours=10.0,
            sla_hours=24.0,
            historical_average_hours=12.0,
        )


def test_optimization_recommendation_schema_valid():
    opt = OptimizationRecommendationSchema(
        id="opt-9901",
        process_id="proc-type-procurement",
        recommendation_type="BOTTLENECK_REDUCTION",
        problem="Manager approval step experiences average delay of 28 hours",
        root_cause="Manual email notifications without escalation triggers",
        evidence={"avg_delay_hours": 28.0, "affected_cases": 45},
        baseline_metric=48.0,
        predicted_metric=16.0,
        improvement_percent=66.6,
        confidence=0.91,
        risk="LOW",
        status="PENDING_APPROVAL",  # Required by Rule #5
    )
    json_str = opt.model_dump_json()
    reconstructed = OptimizationRecommendationSchema.model_validate_json(json_str)
    assert reconstructed == opt
    assert reconstructed.status == "PENDING_APPROVAL"


def test_optimization_recommendation_invalid_risk():
    with pytest.raises(ValidationError):
        OptimizationRecommendationSchema(
            process_id="p-1",
            recommendation_type="TEST",
            problem="Prob",
            root_cause="Cause",
            risk="CRITICAL_RISK",  # Invalid risk literal
        )


def test_email_request_and_result_valid():
    req = EmailRequest(
        recipient="requester@company.com",
        subject="Purchase Request Submitted",
        body="<p>Your request #1001 has been submitted.</p>",
        priority="HIGH",
        process_id="proc-1001",
        task_id="task-501",
        recipient_role="requester",
        template_name="request_submitted.html",
    )
    req_json = req.model_dump_json()
    assert EmailRequest.model_validate_json(req_json) == req

    res = EmailResult(
        status="DRY_RUN",
        message_id="msg-dryrun-001",
        error="",
    )
    res_json = res.model_dump_json()
    assert EmailResult.model_validate_json(res_json) == res


def test_email_request_invalid_priority():
    with pytest.raises(ValidationError):
        EmailRequest(
            recipient="test@example.com",
            subject="Sub",
            body="Body",
            priority="EXTREME",  # Invalid priority
            process_id="p-1",
            task_id="t-1",
        )
