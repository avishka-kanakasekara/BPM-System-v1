"""
Agent 2 — Retry Manager & Recovery Subsystem Tests

Tests hard deterministic overrides and intelligent retry logic:
1. TEMPORARY/TIMEOUT failures retry with exponential backoff delay.
2. Non-idempotent action + UNKNOWN failure type ALWAYS stops after 1 attempt (hard override).
3. AUTHORIZATION failure ALWAYS stops after 1 attempt (hard override).
4. Attempt count >= 3 ALWAYS stops regardless of failure type (hard override).
"""

import pytest

from app.execution import failure_analyzer, retry_manager
from app.execution.execution_engine import execute_with_recovery
from app.llm.gemini_client import GeminiClient
from app.llm.schemas import FailureDiagnosis, RecoveryDecision


# ---------------------------------------------------------------------------
# 1. Hard Deterministic Overrides Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_non_idempotent_unknown_failure_stops():
    # Non-idempotent action + UNKNOWN failure -> Hard override: STOP (retry=False)
    diag = FailureDiagnosis(
        failure_type="UNKNOWN",
        confidence=0.5,
        reasoning="Unclassified custom exception",
        recommended_action="Investigate",
    )
    decision = await retry_manager.evaluate_retry(
        action="unregistered_custom_write_action",
        attempt_number=1,
        diagnosis=diag,
        is_idempotent=False,  # Explicitly non-idempotent
        gemini_client=GeminiClient(is_offline=True),
    )
    assert decision.retry is False
    assert decision.escalate is True
    assert "hard deterministic override" in decision.reasoning.lower()
    assert "non-idempotent" in decision.reasoning.lower()


@pytest.mark.asyncio
async def test_retry_authorization_failure_stops():
    # AUTHORIZATION failure -> Hard override: STOP (retry=False)
    diag = FailureDiagnosis(
        failure_type="AUTHORIZATION",
        confidence=1.0,
        reasoning="HTTP 401 Unauthorized",
        recommended_action="STOP",
    )
    decision = await retry_manager.evaluate_retry(
        action="create_po_draft",
        attempt_number=1,
        diagnosis=diag,
        is_idempotent=True,
        gemini_client=GeminiClient(is_offline=True),
    )
    assert decision.retry is False
    assert decision.escalate is True
    assert "authorization" in decision.reasoning.lower()


@pytest.mark.asyncio
async def test_retry_max_attempts_exceeded_stops():
    # Attempt count >= 3 -> Hard override: STOP (retry=False)
    diag = FailureDiagnosis(
        failure_type="TEMPORARY",
        confidence=0.9,
        reasoning="Transient socket timeout",
        recommended_action="Retry",
    )
    decision = await retry_manager.evaluate_retry(
        action="create_po_draft",
        attempt_number=3,  # 3rd attempt
        diagnosis=diag,
        is_idempotent=True,
        gemini_client=GeminiClient(is_offline=True),
    )
    assert decision.retry is False
    assert decision.escalate is True
    assert "maximum attempt limit" in decision.reasoning.lower()


@pytest.mark.asyncio
async def test_retry_temporary_failure_succeeds_retry():
    # TEMPORARY failure on attempt 1 -> Retry approved (retry=True)
    diag = FailureDiagnosis(
        failure_type="TEMPORARY",
        confidence=0.9,
        reasoning="Transient connection glitch",
        recommended_action="Retry",
    )
    decision = await retry_manager.evaluate_retry(
        action="create_po_draft",
        attempt_number=1,
        diagnosis=diag,
        is_idempotent=True,
        gemini_client=GeminiClient(is_offline=True),
    )
    assert decision.retry is True
    assert decision.delay_seconds == 2  # 2^1 = 2s backoff delay


# ---------------------------------------------------------------------------
# 2. Failure Analyzer Override Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_failure_analyzer_overrides():
    # 401 Unauthorized -> AUTHORIZATION
    diag1 = await failure_analyzer.analyze_failure(
        error_message="HTTP 401 Unauthorized access",
        tool_name="create_po_draft",
    )
    assert diag1.failure_type == "AUTHORIZATION"

    # Timeout -> TIMEOUT
    diag2 = await failure_analyzer.analyze_failure(
        error_message="Connection timed out after 10000ms",
        tool_name="create_po_draft",
        exception_obj=TimeoutError("Socket timeout"),
    )
    assert diag2.failure_type == "TIMEOUT"

    # Duplicate -> DUPLICATE
    diag3 = await failure_analyzer.analyze_failure(
        error_message="Unique constraint violation: key already exists",
        tool_name="create_po_draft",
    )
    assert diag3.failure_type == "DUPLICATE"
