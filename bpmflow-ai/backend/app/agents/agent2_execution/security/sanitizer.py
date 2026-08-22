"""
Agent 2 — Prompt Sanitizer & Injection Defense

Sanitizes untrusted text (purchase request descriptions, email content, process metadata)
before interpolation into Gemini LLM prompts.

Detects, logs, and neutralizes prompt-injection patterns (e.g. "ignore previous instructions",
"system:", attempts to override safety guidelines or alter agent persona).
"""

import logging
import re
from typing import Tuple

logger = logging.getLogger("agent_2.security.sanitizer")

# Patterns matching common prompt injection attacks
INJECTION_PATTERNS = [
    (r"ignore\s+(all\s+)?(previous|prior)\s+instructions", "Instruction override attempt"),
    (r"disregard\s+(all\s+)?(previous|prior)\s+instructions", "Instruction override attempt"),
    (r"forget\s+(all\s+)?(previous|prior)\s+rules", "Rule override attempt"),
    (r"system\s*:", "System prompt spoofing attempt"),
    (r"human\s*:", "Human role spoofing attempt"),
    (r"assistant\s*:", "Assistant role spoofing attempt"),
    (r"you\s+are\s+now\s+a", "Persona redefinition attempt"),
    (r"override\s+(security|safety|rules|policy)", "Security override attempt"),
    (r"bypass\s+(agent4|tool\s*guard|security|approval)", "Bypass attempt"),
    (r"approve\s+(purchase|payment)", "Unauthorized approval directive injection"),
    (r"execute\s+payment", "Unauthorized payment execution directive injection"),
]


def sanitize_prompt_text(text: str) -> Tuple[str, bool, str]:
    """
    Sanitize text before inserting it into Gemini prompt context.

    :param text: Untrusted input string
    :return: Tuple of (cleaned_text, is_flagged, flag_reason)
    """
    if not text:
        return "", False, ""

    is_flagged = False
    reasons = []
    cleaned_text = text

    for pattern, reason in INJECTION_PATTERNS:
        matches = re.findall(pattern, cleaned_text, flags=re.IGNORECASE)
        if matches:
            is_flagged = True
            reasons.append(reason)
            # Neutralize matched patterns by replacing with [NEUTRALIZED INJECTION DETECTED]
            cleaned_text = re.sub(pattern, f"[NEUTRALIZED: {reason}]", cleaned_text, flags=re.IGNORECASE)

    if is_flagged:
        combined_reason = "; ".join(reasons)
        logger.warning(
            f"PROMPT INJECTION FLAGGED: {combined_reason} | Original sample: {text[:100]!r}"
        )
        return cleaned_text, True, combined_reason

    return cleaned_text, False, ""
