"""Opt-in live OpenAI integration smoke test.

Requirements:
- Skipped unless AGENT3_LLM_LIVE_TEST=true and OPENAI_API_KEY is configured.
- Uses fully synthetic, identifier-free context.
- Never prints prompt, response, model text, or API key.
"""

import os
from decimal import Decimal
import pytest

from app.agents.agent3_resources import (
    ExplanationContext,
    RequirementResult,
    RankedHumanCandidate,
    ScoreBreakdown,
    ResourceType,
    OpenAIExplanationGenerator,
    ResilientFallbackExplainer,
    utc_now,
)
from app.tests.conftest import utc_datetime


@pytest.mark.skipif(
    os.getenv("AGENT3_LLM_LIVE_TEST") != "true" or not os.getenv("OPENAI_API_KEY"),
    reason="Opt-in live OpenAI test disabled. Requires AGENT3_LLM_LIVE_TEST=true and OPENAI_API_KEY.",
)
@pytest.mark.asyncio
async def test_live_openai_explanation_smoke():
    """Opt-in smoke test for live OpenAI Responses API integration using synthetic context."""
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    client = AsyncOpenAI(api_key=api_key)

    try:
        generator = OpenAIExplanationGenerator(
            client=client,
            model="gpt-4o-mini",
            timeout=10.0,
            max_output_tokens=100,
        )
        explainer = ResilientFallbackExplainer(enabled=True, llm_generator=generator)

        candidate = RankedHumanCandidate(
            resource_id=utc_now(), # synthetic timestamp UUID placeholder or fixed uuid
            resource_type=ResourceType.HUMAN,
            name="Synthetic Resource",
            rank=1,
            allocation_score=Decimal("0.225"),
            score_breakdown=ScoreBreakdown(
                role_match=Decimal("0.30"),
                skill_match=Decimal("0.25"),
                availability_score=Decimal("0.20"),
                workload_fit=Decimal("0.15"),
                authority_match=Decimal("0.10"),
                total_score=Decimal("0.225"),
            ),
            current_workload_percentage=Decimal("30"),
            projected_workload_percentage=Decimal("40"),
            available_from=utc_datetime(2026, 1, 1),
        )
        context = ExplanationContext(
            human_requirement_result=RequirementResult(
                resource_type=ResourceType.HUMAN,
                eligible_candidates=[candidate],
            )
        )

        explanation = await explainer.generate_explanation(context)

        assert explanation is not None
        assert len(explanation) > 0
        assert "human approval" in explanation.lower() or "approval" in explanation.lower()
    finally:
        await client.close()
