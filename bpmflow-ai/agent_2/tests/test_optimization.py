"""
Agent 2 — Process Optimization Engine Integration Tests

Tests:
1. Full optimization recommendation generation pipeline.
2. Rule #5 enforcement: requires_human_approval is ALWAYS True, status is ALWAYS PENDING_APPROVAL.
3. Grounded evidence content and confidence scoring (0.0 to 1.0).
4. Ballpark improvement estimate (~55% cycle time reduction).
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.llm.gemini_client import GeminiClient
from app.llm.schemas import OptimizationRecommendationSchema
from app.optimization import (
    bottleneck_detector,
    recommendation_engine,
    rework_detector,
    simulation,
    sla_predictor,
)


@pytest.mark.asyncio
async def test_full_optimization_pipeline():
    gemini_client = GeminiClient(is_offline=True)

    proposal = await recommendation_engine.generate_optimization_proposal(
        session=None, process_id="proc-global-procurement", gemini_client=gemini_client
    )

    assert isinstance(proposal, OptimizationRecommendationSchema)
    assert proposal.recommendation_type == "BOTTLENECK_REDUCTION"

    # Enforce Rule #5 Non-Negotiable
    assert proposal.requires_human_approval is True
    assert proposal.status == "PENDING_APPROVAL"

    # Confidence and risk scoring
    assert 0.0 <= proposal.confidence <= 1.0
    assert proposal.risk in ["LOW", "MEDIUM", "HIGH"]

    # Verify evidence details
    assert "bottleneck_stage" in proposal.evidence
    assert proposal.evidence["bottleneck_stage"] == "Manager Approval"
    assert proposal.improvement_percent > 40.0  # In the ballpark of ~55% example


@pytest.mark.asyncio
async def test_sla_risk_predictor():
    # Task at 19.5h elapsed out of 24.0h SLA with 18.27h historical average
    pred = sla_predictor.predict_sla_risk(
        task_id="task-101",
        task_type="Manager Approval",
        elapsed_hours=19.5,
        sla_hours=24.0,
        historical_avg_hours=18.27,
        current_workload=4,
    )
    assert pred.is_at_risk is True
    assert pred.risk_level in ["HIGH", "CRITICAL"]
    assert 0.0 <= pred.breach_probability <= 1.0


def test_process_simulation():
    res = simulation.simulate_to_be_process(
        as_is_bottleneck_hours=18.27,
        as_is_total_cycle_hours=30.68,
        target_bottleneck_hours=6.0,
        rework_reduction_hours=4.0,
    )
    assert res.hours_saved > 15.0
    assert 50.0 <= res.improvement_percentage <= 60.0  # ~55.0% target
