"""Unit tests for Agent 3 pure scoring, budget, and SoD functions."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents.agent3_resources.budget_validation import (
    validate_authorization_limit,
    validate_budget,
    validate_budget_balance,
    validate_cost_centre,
    validate_currency,
    validate_validity_period,
)
from app.agents.agent3_resources.constants import SCORING_WEIGHTS, ExclusionReason
from app.agents.agent3_resources.fixtures import create_budget_evidence, create_human_evidence
from app.agents.agent3_resources.schemas import BudgetResourceRequirement, HumanResourceRequirement
from app.agents.agent3_resources.scoring import (
    build_weighted_components,
    calculate_score_breakdown,
)
from app.agents.agent3_resources.sod_checks import build_sod_exclusion, has_sod_conflict


@pytest.fixture
def evaluation_timestamp():
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class TestScoringPureFunctions:
    def test_weighted_components_are_named_and_numeric(self, evaluation_timestamp):
        resource = create_human_evidence(
            tenant_id=uuid4(),
            reference_timestamp=evaluation_timestamp,
            roles=["developer"],
            mandatory_skills=["python"],
            preferred_skills=["fastapi"],
            authority="senior",
            current_workload=Decimal("30"),
        )
        requirement = HumanResourceRequirement(
            required_roles=["developer"],
            mandatory_skills=["python"],
            preferred_skills=["fastapi"],
            required_authority="senior",
            requester_id=uuid4(),
            task_deadline=evaluation_timestamp,
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )

        breakdown = calculate_score_breakdown(resource, requirement)
        assert breakdown.weighted_components
        for factor in SCORING_WEIGHTS:
            component = breakdown.weighted_components[factor]
            assert component.factor == factor
            assert component.weight == Decimal(str(SCORING_WEIGHTS[factor]))
            expected = (component.raw_score * component.weight).quantize(
                Decimal("0.01"),
                rounding=__import__("decimal").ROUND_HALF_UP,
            )
            assert component.weighted_contribution == expected

        expected_total = sum(
            component.weighted_contribution
            for component in breakdown.weighted_components.values()
        )
        assert breakdown.total_score == expected_total

    def test_build_weighted_components_sums_to_total(self):
        components = build_weighted_components(
            Decimal("1.0"),
            Decimal("0.50"),
            Decimal("1.0"),
            Decimal("0.70"),
            Decimal("1.0"),
        )
        total = sum(component.weighted_contribution for component in components.values())
        assert total <= Decimal("1.0")


class TestBudgetValidationPureFunctions:
    def test_balance_and_authorization_checks(self):
        assert validate_budget_balance(Decimal("1000"), Decimal("500")) is True
        assert validate_budget_balance(Decimal("100"), Decimal("500")) is False
        assert validate_authorization_limit(Decimal("500"), Decimal("1000")) is True
        assert validate_authorization_limit(Decimal("1500"), Decimal("1000")) is False

    def test_cost_centre_and_currency_checks(self):
        assert validate_cost_centre("CC-DEMO", "CC-DEMO") is True
        assert validate_cost_centre("CC-DEMO", "CC-OTHER") is False
        assert validate_cost_centre(None, "CC-DEMO") is True
        assert validate_currency("USD", "USD") is True
        assert validate_currency("USD", "EUR") is False

    def test_validity_period(self, evaluation_timestamp):
        future = evaluation_timestamp.replace(year=2027)
        past = evaluation_timestamp.replace(year=2024)
        assert validate_validity_period(evaluation_timestamp, future) is True
        assert validate_validity_period(evaluation_timestamp, past) is False
        assert validate_validity_period(evaluation_timestamp, None) is True

    def test_validate_budget_composes_all_checks(self, evaluation_timestamp):
        budget = create_budget_evidence(
            tenant_id=uuid4(),
            reference_timestamp=evaluation_timestamp,
            available_balance=Decimal("50000"),
            currency="USD",
            cost_centre="CC-DEMO",
            authorization_limit=Decimal("25000"),
        )
        requirement = BudgetResourceRequirement(
            required_amount=Decimal("10000"),
            currency="USD",
            cost_centre="CC-DEMO",
            requester_id=uuid4(),
            task_deadline=evaluation_timestamp,
            process_stage="resource_allocation",
        )
        result = validate_budget(budget, requirement, evaluation_timestamp)
        assert result.sufficient_balance is True
        assert result.cost_centre_match is True
        assert result.currency_match is True
        assert result.validity_period_valid is True
        assert result.within_authorization_limit is True


class TestSodChecksPureFunctions:
    def test_has_sod_conflict(self):
        conflict_id = uuid4()
        assert has_sod_conflict([conflict_id]) is True
        assert has_sod_conflict([]) is False

    def test_build_sod_exclusion(self):
        conflict_id = uuid4()
        entry = build_sod_exclusion([conflict_id], resource_name="Epsilon")
        assert entry is not None
        assert entry.reason == ExclusionReason.SEGREGATION_OF_DUTIES_VIOLATION
        assert "Epsilon" in entry.description
        assert build_sod_exclusion([]) is None
