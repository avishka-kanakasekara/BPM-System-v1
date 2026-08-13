"""BUDGET resource validation strategy."""

from datetime import datetime
from typing import List

from ..interfaces import ResourceRepository
from ..schemas import (
    RequirementResult,
    BudgetResourceEvidence,
    BudgetResourceRequirement,
    BudgetValidationChecks,
)
from ..constants import ResourceType
from ..retrieval import CandidateRetriever
from .base import ResourceStrategy


class BudgetResourceStrategy(ResourceStrategy):
    """Strategy for BUDGET resource validation.
    
    BUDGET validation is separate from HUMAN ranking.
    Does not apply the HUMAN scoring formula.
    """

    def __init__(self, repository: ResourceRepository):
        """Initialize with a resource repository."""
        self.repository = repository
        self.retriever = CandidateRetriever(repository)

    async def process_requirement(
        self,
        requirement: BudgetResourceRequirement,
        tenant_id: UUID,
        evaluation_timestamp: datetime,
    ) -> RequirementResult:
        """Process a BUDGET resource requirement.

        Pipeline:
        1. Retrieve budget resources (tenant-scoped only)
        2. Validate budget constraints
        3. Return validation results

        Note: BUDGET resources are not ranked like HUMAN resources.
        They are either valid or invalid based on constraints.
        """
        budget_resources = await self.retriever.retrieve_budget_candidates(
            tenant_id=tenant_id,
            evaluation_timestamp=evaluation_timestamp,
        )
        
        # For MVP, assume single budget resource per tenant
        # Take the first available budget resource
        if not budget_resources:
            return RequirementResult(
                resource_type=ResourceType.BUDGET,
                eligible_candidates=[],
                excluded_resources=[],
                budget_validation=None,
            )
        
        budget = budget_resources[0]
        
        # Step 2: Validate budget constraints
        validation = self._validate_budget(budget, requirement, evaluation_timestamp)
        
        # Step 3: Return results
        return RequirementResult(
            resource_type=ResourceType.BUDGET,
            eligible_candidates=[],
            excluded_resources=[],
            budget_validation=validation,
        )

    def _validate_budget(
        self,
        budget: BudgetResourceEvidence,
        requirement: BudgetResourceRequirement,
        evaluation_timestamp: datetime,
    ) -> BudgetValidationChecks:
        """Validate budget against requirements.
        
        Checks:
        1. Sufficient available balance
        2. Cost-centre match
        3. Currency match
        4. Validity period
        5. Authorization limit
        """
        # Check 1: Sufficient balance
        sufficient_balance = budget.available_balance >= requirement.required_amount
        
        # Check 2: Cost-centre match
        cost_centre_match = True
        if requirement.cost_centre and budget.cost_centre:
            cost_centre_match = budget.cost_centre == requirement.cost_centre
        
        # Check 3: Currency match
        currency_match = budget.currency == requirement.currency
        
        # Check 4: Validity period
        validity_period_valid = True
        if budget.valid_until:
            validity_period_valid = evaluation_timestamp <= budget.valid_until
        
        # Check 5: Authorization limit
        within_authorization_limit = True
        if budget.authorization_limit:
            within_authorization_limit = requirement.required_amount <= budget.authorization_limit
        
        return BudgetValidationChecks(
            resource_id=budget.resource_id,
            name=budget.name,
            sufficient_balance=sufficient_balance,
            cost_centre_match=cost_centre_match,
            currency_match=currency_match,
            validity_period_valid=validity_period_valid,
            within_authorization_limit=within_authorization_limit,
            available_balance=budget.available_balance,
            required_amount=requirement.required_amount,
            evidence_references=budget.evidence_references,
        )
