"""Tests for BUDGET validation strategy."""

import pytest
from datetime import timedelta
from decimal import Decimal

pytestmark = pytest.mark.anyio

from app.agents.agent3_resources import (
    BudgetResourceStrategy,
    InMemoryResourceRepository,
    create_budget_evidence,
    create_budget_requirement,
    get_tenant_a_id,
    get_resource_id_1,
    get_requester_id,
)


def _budget(evaluation_timestamp, **overrides):
    return create_budget_evidence(
        tenant_id=get_requester_id(),
        reference_timestamp=evaluation_timestamp,
        **overrides,
    )


def _requirement(evaluation_timestamp, **overrides):
    return create_budget_requirement(
        tenant_id=get_tenant_a_id(),
        requester_id=get_requester_id(),
        reference_timestamp=evaluation_timestamp,
        **overrides,
    )


class TestBudgetValidation:
    """Test BUDGET validation checks."""

    async def test_budget_balance_validation(self, evaluation_timestamp):
        """Test budget balance validation."""
        repository = InMemoryResourceRepository()
        strategy = BudgetResourceStrategy(repository)
        
        budget = _budget(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            available_balance=Decimal("10000"),
        )
        repository.add_budget_resource(budget)

        requirement = _requirement(
            evaluation_timestamp,
            required_amount=Decimal("5000"),
            currency="USD",
            cost_centre="CC001",
        )
        
        result = await strategy.process_requirement(requirement, evaluation_timestamp)
        
        assert result is not None
        assert result.budget_validation is not None
        assert result.budget_validation.sufficient_balance is True

    async def test_budget_balance_insufficient(self, evaluation_timestamp):
        """Test budget balance validation when insufficient."""
        repository = InMemoryResourceRepository()
        strategy = BudgetResourceStrategy(repository)
        
        budget = _budget(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            available_balance=Decimal("1000"),
        )
        repository.add_budget_resource(budget)

        requirement = _requirement(
            evaluation_timestamp,
            required_amount=Decimal("5000"),
            currency="USD",
            cost_centre="CC001",
        )
        
        result = await strategy.process_requirement(requirement, evaluation_timestamp)
        
        assert result is not None
        assert result.budget_validation is not None
        assert result.budget_validation.sufficient_balance is False

    async def test_budget_cost_centre_match(self, evaluation_timestamp):
        """Test budget cost-centre validation."""
        repository = InMemoryResourceRepository()
        strategy = BudgetResourceStrategy(repository)
        
        budget = _budget(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            cost_centre="CC001",
        )
        repository.add_budget_resource(budget)

        requirement = _requirement(
            evaluation_timestamp,
            cost_centre="CC001",
            currency="USD",
        )
        
        result = await strategy.process_requirement(requirement, evaluation_timestamp)
        
        assert result is not None
        assert result.budget_validation is not None
        assert result.budget_validation.cost_centre_match is True

    async def test_budget_cost_centre_mismatch(self, evaluation_timestamp):
        """Test budget cost-centre validation when mismatched."""
        repository = InMemoryResourceRepository()
        strategy = BudgetResourceStrategy(repository)
        
        budget = _budget(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            cost_centre="CC001",
        )
        repository.add_budget_resource(budget)

        requirement = _requirement(
            evaluation_timestamp,
            cost_centre="CC002",
            currency="USD",
        )
        
        result = await strategy.process_requirement(requirement, evaluation_timestamp)
        
        assert result is not None
        assert result.budget_validation is not None
        assert result.budget_validation.cost_centre_match is False

    async def test_budget_currency_match(self, evaluation_timestamp):
        """Test budget currency validation."""
        repository = InMemoryResourceRepository()
        strategy = BudgetResourceStrategy(repository)
        
        budget = _budget(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            currency="USD",
        )
        repository.add_budget_resource(budget)

        requirement = _requirement(
            evaluation_timestamp,
            currency="USD",
        )
        
        result = await strategy.process_requirement(requirement, evaluation_timestamp)
        
        assert result is not None
        assert result.budget_validation is not None
        assert result.budget_validation.currency_match is True

    async def test_budget_currency_mismatch(self, evaluation_timestamp):
        """Test budget currency validation when mismatched."""
        repository = InMemoryResourceRepository()
        strategy = BudgetResourceStrategy(repository)
        
        budget = _budget(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            currency="USD",
        )
        repository.add_budget_resource(budget)

        requirement = _requirement(
            evaluation_timestamp,
            currency="EUR",
        )
        
        result = await strategy.process_requirement(requirement, evaluation_timestamp)
        
        assert result is not None
        assert result.budget_validation is not None
        assert result.budget_validation.currency_match is False

    async def test_budget_validity_period(self, evaluation_timestamp):
        """Test budget validity period validation."""
        repository = InMemoryResourceRepository()
        strategy = BudgetResourceStrategy(repository)
        
        budget = _budget(evaluation_timestamp, resource_id=get_resource_id_1())
        budget.valid_until = evaluation_timestamp + timedelta(days=365)
        repository.add_budget_resource(budget)

        requirement = _requirement(evaluation_timestamp)
        
        result = await strategy.process_requirement(requirement, evaluation_timestamp)
        
        assert result.budget_validation is not None
        assert result.budget_validation.validity_period_valid is True

    async def test_budget_validity_period_expired(self, evaluation_timestamp):
        """Test budget validity period validation when expired."""
        repository = InMemoryResourceRepository()
        strategy = BudgetResourceStrategy(repository)
        
        budget = _budget(evaluation_timestamp, resource_id=get_resource_id_1())
        budget.valid_until = evaluation_timestamp - timedelta(days=30)
        repository.add_budget_resource(budget)

        requirement = _requirement(evaluation_timestamp)
        
        result = await strategy.process_requirement(requirement, evaluation_timestamp)
        
        assert result.budget_validation is not None
        assert result.budget_validation.validity_period_valid is False

    async def test_budget_authorization_limit(self, evaluation_timestamp):
        """Test budget authorization limit validation."""
        repository = InMemoryResourceRepository()
        strategy = BudgetResourceStrategy(repository)
        
        budget = _budget(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            authorization_limit=Decimal("10000"),
        )
        repository.add_budget_resource(budget)

        requirement = _requirement(
            evaluation_timestamp,
            required_amount=Decimal("5000"),
            currency="USD",
        )
        
        result = await strategy.process_requirement(requirement, evaluation_timestamp)
        
        assert result is not None
        assert result.budget_validation is not None
        assert result.budget_validation.within_authorization_limit is True

    async def test_budget_authorization_limit_exceeded(self, evaluation_timestamp):
        """Test budget authorization limit validation when exceeded."""
        repository = InMemoryResourceRepository()
        strategy = BudgetResourceStrategy(repository)
        
        budget = _budget(
            evaluation_timestamp,
            resource_id=get_resource_id_1(),
            authorization_limit=Decimal("3000"),
        )
        repository.add_budget_resource(budget)

        requirement = _requirement(
            evaluation_timestamp,
            required_amount=Decimal("5000"),
            currency="USD",
        )
        
        result = await strategy.process_requirement(requirement, evaluation_timestamp)
        
        assert result is not None
        assert result.budget_validation is not None
        assert result.budget_validation.within_authorization_limit is False

    async def test_budget_not_human_substitute(self, evaluation_timestamp):
        """Test that BUDGET is not a HUMAN substitute."""
        repository = InMemoryResourceRepository()
        strategy = BudgetResourceStrategy(repository)
        
        budget = _budget(evaluation_timestamp, resource_id=get_resource_id_1())
        repository.add_budget_resource(budget)

        requirement = _requirement(evaluation_timestamp, currency="USD")
        
        result = await strategy.process_requirement(requirement, evaluation_timestamp)
        
        assert result is not None
        # BUDGET should not return eligible candidates like HUMAN strategy
        assert len(result.eligible_candidates) == 0

    async def test_human_formula_not_applied_to_budget(self, evaluation_timestamp):
        """Test that HUMAN scoring formula is not applied to BUDGET."""
        repository = InMemoryResourceRepository()
        strategy = BudgetResourceStrategy(repository)
        
        budget = _budget(evaluation_timestamp, resource_id=get_resource_id_1())
        repository.add_budget_resource(budget)

        requirement = _requirement(evaluation_timestamp, currency="USD")
        
        result = await strategy.process_requirement(requirement, evaluation_timestamp)
        
        assert result is not None
        # BUDGET validation should not include score breakdown
        assert result.budget_validation is not None
        # No ranked candidates for budget
        assert len(result.eligible_candidates) == 0
