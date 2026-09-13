"""Pure budget validation functions for Agent 3."""

from __future__ import annotations

from datetime import datetime

from .schemas import (
    BudgetResourceEvidence,
    BudgetResourceRequirement,
    BudgetValidationChecks,
)


def validate_budget_balance(
    available_balance,
    required_amount,
) -> bool:
    """Return True when available balance covers the required amount."""
    return available_balance >= required_amount


def validate_cost_centre(
    budget_cost_centre: str | None,
    required_cost_centre: str | None,
) -> bool:
    """Return True when cost centres match or no cost centre is required."""
    if not required_cost_centre or not budget_cost_centre:
        return True
    return budget_cost_centre == required_cost_centre


def validate_currency(budget_currency: str, required_currency: str) -> bool:
    """Return True when currencies match exactly."""
    return budget_currency == required_currency


def validate_validity_period(
    evaluation_timestamp: datetime,
    valid_until: datetime | None,
) -> bool:
    """Return True when the budget is still valid at evaluation time."""
    if valid_until is None:
        return True
    return evaluation_timestamp <= valid_until


def validate_authorization_limit(
    required_amount,
    authorization_limit,
) -> bool:
    """Return True when required amount is within the authorization limit."""
    if authorization_limit is None:
        return True
    return required_amount <= authorization_limit


def validate_budget(
    budget: BudgetResourceEvidence,
    requirement: BudgetResourceRequirement,
    evaluation_timestamp: datetime,
) -> BudgetValidationChecks:
    """Validate a budget resource against allocation requirements."""
    return BudgetValidationChecks(
        resource_id=budget.resource_id,
        name=budget.name,
        sufficient_balance=validate_budget_balance(
            budget.available_balance,
            requirement.required_amount,
        ),
        cost_centre_match=validate_cost_centre(
            budget.cost_centre,
            requirement.cost_centre,
        ),
        currency_match=validate_currency(budget.currency, requirement.currency),
        validity_period_valid=validate_validity_period(
            evaluation_timestamp,
            budget.valid_until,
        ),
        within_authorization_limit=validate_authorization_limit(
            requirement.required_amount,
            budget.authorization_limit,
        ),
        available_balance=budget.available_balance,
        required_amount=requirement.required_amount,
        evidence_references=budget.evidence_references,
    )
