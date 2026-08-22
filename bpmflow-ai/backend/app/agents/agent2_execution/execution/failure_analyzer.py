"""
Agent 2 — Failure Analyzer

Classifies execution exceptions into 9 failure types:
TEMPORARY / PERMANENT / AUTHORIZATION / VALIDATION / DATA / DUPLICATE / TIMEOUT / RATE_LIMIT / UNKNOWN

Applies deterministic overrides for unambiguous errors (401/403 → AUTHORIZATION, TimeoutError → TIMEOUT)
and uses Gemini for ambiguous edge cases.
"""

import asyncio
from typing import Optional
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.llm.prompts import SYSTEM_PROMPT_FAILURE_CLASSIFICATION
from app.agents.agent2_execution.llm.schemas import FailureDiagnosis


async def analyze_failure(
    error_message: str,
    tool_name: str,
    attempt_number: int = 1,
    exception_obj: Optional[Exception] = None,
    gemini_client: Optional[GeminiClient] = None,
) -> FailureDiagnosis:
    """
    Diagnose an execution failure and return a structured FailureDiagnosis object.

    :param error_message: Text description of the error
    :param tool_name: Name of the tool that failed
    :param attempt_number: Current attempt count
    :param exception_obj: Caught Python Exception instance (optional)
    :param gemini_client: GeminiClient instance (optional)
    :return: Structured FailureDiagnosis model instance
    """
    err_lower = error_message.lower() if error_message else ""
    exc_type = exception_obj.__class__.__name__ if exception_obj else ""

    # ---------------------------------------------------------------------------
    # Deterministic Overrides for Unambiguous Error Cases
    # ---------------------------------------------------------------------------

    # Override 1: Authorization & Permission Errors (401 / 403 / forbidden)
    if "401" in err_lower or "403" in err_lower or "unauthorized" in err_lower or "forbidden" in err_lower:
        return FailureDiagnosis(
            failure_type="AUTHORIZATION",
            confidence=1.0,
            reasoning=f"Deterministic override: Authorization/permission denied error ({error_message})",
            recommended_action="STOP execution and raise security log event",
        )

    # Override 2: Timeouts
    if isinstance(exception_obj, (TimeoutError, asyncio.TimeoutError)) or "timeout" in err_lower or "timed out" in err_lower:
        return FailureDiagnosis(
            failure_type="TIMEOUT",
            confidence=1.0,
            reasoning=f"Deterministic override: Network or connection socket timeout ({error_message})",
            recommended_action="Retry using exponential backoff strategy",
        )

    # Override 3: Duplicate / Idempotency Key Conflicts
    if "duplicate" in err_lower or "unique constraint" in err_lower or "already exists" in err_lower:
        return FailureDiagnosis(
            failure_type="DUPLICATE",
            confidence=1.0,
            reasoning=f"Deterministic override: Duplicate constraint violation ({error_message})",
            recommended_action="Fetch existing execution receipt",
        )

    # Override 4: Rate Limits (429)
    if "429" in err_lower or "rate limit" in err_lower or "too many requests" in err_lower:
        return FailureDiagnosis(
            failure_type="RATE_LIMIT",
            confidence=1.0,
            reasoning=f"Deterministic override: API rate limit exceeded ({error_message})",
            recommended_action="Retry with extended backoff delay",
        )

    # Override 5: Schema Validation Errors
    if "validation" in err_lower or "missing required field" in err_lower or "invalid input" in err_lower:
        return FailureDiagnosis(
            failure_type="VALIDATION",
            confidence=1.0,
            reasoning=f"Deterministic override: Input schema validation error ({error_message})",
            recommended_action="Correct parameter inputs before retrying",
        )

    # ---------------------------------------------------------------------------
    # Gemini LLM Classification Fallback for Ambiguous Errors
    # ---------------------------------------------------------------------------
    client = gemini_client or GeminiClient()
    prompt_text = (
        f"Tool Name: {tool_name}\n"
        f"Attempt Number: {attempt_number}\n"
        f"Error Type: {exc_type}\n"
        f"Error Message: {error_message}\n"
        f"Classify this failure into one of the 9 taxonomy types."
    )

    try:
        diag = await client.generate_structured_output(
            prompt=prompt_text,
            response_schema=FailureDiagnosis,
            system_instruction=SYSTEM_PROMPT_FAILURE_CLASSIFICATION,
            model_tier="flash",
        )
        return diag
    except Exception:
        # Fallback if Gemini fails
        return FailureDiagnosis(
            failure_type="UNKNOWN",
            confidence=0.5,
            reasoning=f"Unclassified system exception: {error_message}",
            recommended_action="Investigate system error logs",
        )
