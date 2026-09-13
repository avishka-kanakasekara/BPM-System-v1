"""Tests for Agent 3 advisory-only enforcement."""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents.agent3_resources.advisory import (
    AdvisoryViolationError,
    assert_advisory_recommendation,
)
from app.agents.agent3_resources.constants import RecommendationStatus
from app.agents.agent3_resources.schemas import (
    AgentMessageMetadata,
    AllocationRecommendation,
    MessageType,
)


def _metadata():
    return AgentMessageMetadata(
        correlation_id=uuid4(),
        process_instance_id=uuid4(),
        task_id=uuid4(),
        tenant_id=uuid4(),
        message_type=MessageType.RESOURCE_ALLOCATION_RESPONSE,
    )


def test_advisory_recommendation_passes():
    recommendation = AllocationRecommendation(
        metadata=_metadata(),
        status=RecommendationStatus.PENDING_HUMAN_APPROVAL,
        requires_human_approval=True,
        explanation="Advisory only",
        confidence=Decimal("0.85"),
    )
    assert_advisory_recommendation(recommendation)


def test_advisory_recommendation_rejects_missing_human_approval():
    recommendation = AllocationRecommendation.model_construct(
        metadata=_metadata(),
        status=RecommendationStatus.PENDING_HUMAN_APPROVAL,
        requires_human_approval=False,
        explanation="Advisory only",
        confidence=Decimal("0.85"),
    )
    with pytest.raises(AdvisoryViolationError):
        assert_advisory_recommendation(recommendation)
