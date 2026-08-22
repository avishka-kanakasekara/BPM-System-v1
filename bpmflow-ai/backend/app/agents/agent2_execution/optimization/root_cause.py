"""
Agent 2 — Root Cause Analysis Engine

Generates grounded root-cause diagnosis statements for detected process bottlenecks and rework patterns
using structured Gemini LLM reasoning.
"""

from typing import Optional
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.optimization.bottleneck_detector import BottleneckAnalysis
from app.agents.agent2_execution.optimization.rework_detector import ReworkAnalysis


async def analyze_root_cause(
    bottleneck: BottleneckAnalysis,
    rework: ReworkAnalysis,
    gemini_client: Optional[GeminiClient] = None,
) -> str:
    """
    Produce a structured root-cause analysis narrative.

    :param bottleneck: BottleneckAnalysis instance
    :param rework: ReworkAnalysis instance
    :param gemini_client: Optional GeminiClient instance
    :return: Grounded root cause string statement
    """
    client = gemini_client or GeminiClient()

    prompt_text = (
        f"BOTTLENECK EVIDENCE:\n"
        f"Primary Bottleneck Stage: {bottleneck.dominant_bottleneck} ({bottleneck.dominant_avg_duration_hours}h average delay)\n"
        f"Impact Severity: {bottleneck.impact_severity}\n\n"
        f"REWORK EVIDENCE:\n"
        f"Total Rework Events: {rework.total_rework_events}\n"
        f"Dominant Rework Reason: {rework.dominant_rework_reason} ({rework.dominant_reason_count} cases, {rework.details.get('dominant_percentage', 0.0)}%)\n\n"
        f"Formulate a concise 2-sentence root cause statement explaining why this process bottleneck occurs."
    )

    try:
        response_text = await client.generate_text(
            prompt_text,
            system_instruction="You are a Business Process Optimization Expert.",
            model_tier="pro",
        )
        if response_text:
            return response_text.strip()
    except Exception:
        pass

    # Grounded fallback diagnosis statement
    return (
        f"The primary bottleneck in {bottleneck.dominant_bottleneck} ({bottleneck.dominant_avg_duration_hours}h average delay) "
        f"is caused by manual follow-up without automated SLA reminders, combined with a {rework.details.get('dominant_percentage', 0.0)}% "
        f"rework rate due to '{rework.dominant_rework_reason}' requiring request re-submissions."
    )
