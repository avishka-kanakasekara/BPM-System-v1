"""
Agent 2 — Gemini Client Unit & Integration Tests (Offline Mode)

Tests:
1. Structured decision calls returning schema-valid Pydantic models.
2. Function calling proposals returning one of the 12 declared tools with valid parameters.
3. Safety directives in system prompts.
4. Completeness of function declarations (all 12 tools).
"""

import pytest

from app.llm import function_declarations, prompts
from app.llm.gemini_client import GeminiClient
from app.llm.schemas import (
    AgentDecision,
    CycleStepDecision,
    ExecutionPlan,
    FailureDiagnosis,
    OptimizationRecommendationSchema,
    RecoveryDecision,
    ToolCallContract,
)


@pytest.fixture
def offline_client():
    """Returns a GeminiClient forced to offline mode for deterministic testing."""
    return GeminiClient(is_offline=True)


# ---------------------------------------------------------------------------
# 1. Structured Output Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_structured_output_execution_plan(offline_client):
    plan = await offline_client.generate_structured_output(
        prompt="Create an execution plan for purchase request #1001",
        response_schema=ExecutionPlan,
        system_instruction=prompts.SYSTEM_PROMPT_PLANNING,
        model_tier="pro",
    )
    assert isinstance(plan, ExecutionPlan)
    assert plan.task_id != ""
    assert len(plan.steps) > 0
    assert plan.risk_level in ["LOW", "MEDIUM", "HIGH"]
    assert 0.0 <= plan.confidence <= 1.0


@pytest.mark.asyncio
async def test_structured_output_agent_decision(offline_client):
    decision = await offline_client.generate_structured_output(
        prompt="Decide next step for purchase request validation",
        response_schema=AgentDecision,
        system_instruction=prompts.BASE_SAFETY_DIRECTIVE,
        model_tier="flash",
    )
    assert isinstance(decision, AgentDecision)
    assert decision.decision in ["EXECUTE", "ESCALATE", "REJECT"]
    assert 0.0 <= decision.confidence <= 1.0


@pytest.mark.asyncio
async def test_structured_output_cycle_step_complete_after_success(offline_client):
    step = await offline_client.generate_structured_output(
        prompt=(
            "ASSIGNED OBJECTIVE: Send finance reminder\n"
            "OBSERVATIONS:\n1. tool=send_email status=SUCCESS error=none result={}\n"
        ),
        response_schema=CycleStepDecision,
        system_instruction=prompts.SYSTEM_PROMPT_LOOP,
        model_tier="pro",
    )
    assert isinstance(step, CycleStepDecision)
    assert step.next_action == "COMPLETE"
    assert step.goal_achieved is True


@pytest.mark.asyncio
async def test_structured_output_failure_diagnosis(offline_client):
    diag = await offline_client.generate_structured_output(
        prompt="Diagnose ERP API socket timeout exception",
        response_schema=FailureDiagnosis,
        system_instruction=prompts.SYSTEM_PROMPT_FAILURE_CLASSIFICATION,
        model_tier="flash",
    )
    assert isinstance(diag, FailureDiagnosis)
    assert diag.failure_type in [
        "TEMPORARY", "TIMEOUT", "DUPLICATE", "RATE_LIMIT",
        "VALIDATION", "AUTHORIZATION", "DATA", "PERMANENT", "UNKNOWN"
    ]
    assert 0.0 <= diag.confidence <= 1.0


@pytest.mark.asyncio
async def test_structured_output_recovery_decision(offline_client):
    recovery = await offline_client.generate_structured_output(
        prompt="Formulate recovery plan for TEMPORARY socket error",
        response_schema=RecoveryDecision,
        system_instruction=prompts.SYSTEM_PROMPT_RECOVERY,
        model_tier="flash",
    )
    assert isinstance(recovery, RecoveryDecision)
    assert isinstance(recovery.retry, bool)
    assert recovery.delay_seconds >= 0


@pytest.mark.asyncio
async def test_structured_output_optimization_recommendation(offline_client):
    opt = await offline_client.generate_structured_output(
        prompt="Generate optimization proposal for manager approval bottleneck",
        response_schema=OptimizationRecommendationSchema,
        system_instruction=prompts.SYSTEM_PROMPT_PROCESS_OPTIMIZATION,
        model_tier="pro",
    )
    assert isinstance(opt, OptimizationRecommendationSchema)
    assert opt.status == "PENDING_APPROVAL"  # Rule #5 non-negotiable invariant
    assert opt.problem != ""


# ---------------------------------------------------------------------------
# 2. Function Calling Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_function_calling_proposal(offline_client):
    tool_call = await offline_client.generate_function_call(
        prompt="Draft PO for vendor v-100 amount 3400.00",
        system_instruction=prompts.BASE_SAFETY_DIRECTIVE,
        model_tier="flash",
    )
    assert isinstance(tool_call, ToolCallContract)
    assert tool_call.name in [tool["name"] for tool in function_declarations.ALL_TOOL_DECLARATIONS]
    assert isinstance(tool_call.parameters, dict)


# ---------------------------------------------------------------------------
# 3. Function Declarations & Prompts Integrity Tests
# ---------------------------------------------------------------------------

def test_all_12_tools_declared():
    expected_tools = {
        "create_workflow_task",
        "update_task",
        "send_email",
        "send_reminder",
        "create_po_draft",
        "request_quotation",
        "update_procurement_record",
        "schedule_escalation",
        "create_exception",
        "get_process_history",
        "get_task_history",
        "calculate_kpi",
    }
    declared_names = {tool["name"] for tool in function_declarations.ALL_TOOL_DECLARATIONS}
    assert declared_names == expected_tools


def test_system_prompts_safety_directives():
    for prompt_text in [
        prompts.SYSTEM_PROMPT_REASONING,
        prompts.SYSTEM_PROMPT_PLANNING,
        prompts.SYSTEM_PROMPT_LOOP,
        prompts.SYSTEM_PROMPT_FAILURE_CLASSIFICATION,
        prompts.SYSTEM_PROMPT_RECOVERY,
        prompts.SYSTEM_PROMPT_PROCESS_OPTIMIZATION,
        prompts.SYSTEM_PROMPT_EMAIL_DRAFTING,
    ]:
        assert "PROPOSE" in prompt_text or "propose" in prompt_text
        assert "NEVER execute" in prompt_text or "never execute" in prompt_text
