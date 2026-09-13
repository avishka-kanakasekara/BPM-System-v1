"""BUDGET resource validation strategy."""

from datetime import datetime
from uuid import UUID

from ..budget_validation import validate_budget
from ..constants import ResourceType
from ..interfaces import ResourceRepository
from ..retrieval import CandidateRetriever
from ..schemas import (
    BudgetResourceRequirement,
    RequirementResult,
)
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
        
        validation = validate_budget(budget, requirement, evaluation_timestamp)

        return RequirementResult(
            resource_type=ResourceType.BUDGET,
            eligible_candidates=[],
            excluded_resources=[],
            budget_validation=validation,
        )
