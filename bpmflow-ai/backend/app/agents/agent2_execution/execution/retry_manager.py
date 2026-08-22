"""
Agent 2 — Intelligent Retry Manager

Evaluates recovery decisions combining failure taxonomy, retry history, tool reliability,
SLA hours remaining, idempotency, and attempt count.

Applies HARD DETERMINISTIC OVERRIDES that Gemini CANNOT override:
1. Non-idempotent action + UNKNOWN failure type → Always STOP (no retry).
2. AUTHORIZATION failures → Always STOP (no retry) & escalate.
3. More than 3 attempts (attempt_number >= 3) → Always STOP (no retry).
"""

from typing import Optional
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.llm.prompts import SYSTEM_PROMPT_RECOVERY
from app.agents.agent2_execution.llm.schemas import FailureDiagnosis, RecoveryDecision

# List of actions considered idempotent
IDEMPOTENT_ACTIONS = {
    "create_workflow_task",
    "update_task",
    "send_email",
    "send_reminder",
    "schedule_reminder",
    "create_po_draft",
    "request_quotation",
    "update_procurement_record",
    "schedule_escalation",
    "create_exception",
    "get_process_history",
    "get_task_history",
    "calculate_kpi",
}


def is_action_idempotent(action_name: str) -> bool:
    """Check if an action is known to be idempotent."""
    return action_name.strip().lower() in IDEMPOTENT_ACTIONS


async def evaluate_retry(
    action: str,
    attempt_number: int,
    diagnosis: FailureDiagnosis,
    is_idempotent: Optional[bool] = None,
    gemini_client: Optional[GeminiClient] = None,
) -> RecoveryDecision:
    """
    Evaluate whether to retry a failed tool action, apply backoff delay, or escalate.

    :param action: Tool/action name
    :param attempt_number: Current attempt count (1-indexed)
    :param diagnosis: FailureDiagnosis object from failure_analyzer
    :param is_idempotent: Optional override boolean for idempotency
    :param gemini_client: Optional GeminiClient instance
    :return: RecoveryDecision schema
    """
    act_clean = action.strip().lower()
    idempotent = is_idempotent if is_idempotent is not None else is_action_idempotent(act_clean)
    ftype = diagnosis.failure_type

    # ---------------------------------------------------------------------------
    # HARD DETERMINISTIC OVERRIDES (Gemini CANNOT override these)
    # ---------------------------------------------------------------------------

    # Hard Override 1: Attempt Limit (>= 3) -> Always STOP
    if attempt_number >= 3:
        return RecoveryDecision(
            retry=False,
            delay_seconds=0,
            alternative_strategy="",
            escalate=True,
            reasoning=f"Hard deterministic override: Maximum attempt limit ({attempt_number}/3) reached. Execution stopped.",
        )

    # Hard Override 2: AUTHORIZATION Failures -> Always STOP
    if ftype == "AUTHORIZATION":
        return RecoveryDecision(
            retry=False,
            delay_seconds=0,
            alternative_strategy="",
            escalate=True,
            reasoning="Hard deterministic override: AUTHORIZATION failure requires security escalation. Execution stopped.",
        )

    # Hard Override 3: Non-idempotent action + UNKNOWN failure -> Always STOP
    if not idempotent and ftype == "UNKNOWN":
        return RecoveryDecision(
            retry=False,
            delay_seconds=0,
            alternative_strategy="Request human manual review",
            escalate=True,
            reasoning="Hard deterministic override: Non-idempotent action with UNKNOWN failure must not be retried to prevent unsafe side effects.",
        )

    # ---------------------------------------------------------------------------
    # Deterministic Rules for Standard Retryable Failures
    # ---------------------------------------------------------------------------
    if ftype in ["TEMPORARY", "TIMEOUT", "RATE_LIMIT"]:
        backoff_delay = 2 ** attempt_number  # 2s, 4s, 8s exponential backoff
        return RecoveryDecision(
            retry=True,
            delay_seconds=backoff_delay,
            alternative_strategy="Retry using exponential backoff delay",
            escalate=False,
            reasoning=f"Standard recovery rule: Retryable {ftype} failure. Scheduling retry attempt {attempt_number + 1} with {backoff_delay}s delay.",
        )

    # ---------------------------------------------------------------------------
    # Gemini Fallback for Complex / Ambiguous Cases
    # ---------------------------------------------------------------------------
    client = gemini_client or GeminiClient()
    prompt_text = (
        f"Action: {action}\n"
        f"Attempt Number: {attempt_number}\n"
        f"Idempotent: {idempotent}\n"
        f"Failure Type: {ftype}\n"
        f"Reasoning: {diagnosis.reasoning}\n"
        f"Formulate a recovery decision."
    )

    try:
        dec = await client.generate_structured_output(
            prompt=prompt_text,
            response_schema=RecoveryDecision,
            system_instruction=SYSTEM_PROMPT_RECOVERY,
            model_tier="flash",
        )
        return dec
    except Exception:
        return RecoveryDecision(
            retry=False,
            delay_seconds=0,
            alternative_strategy="",
            escalate=True,
            reasoning="Fallback error: Defaulting to escalation",
        )
