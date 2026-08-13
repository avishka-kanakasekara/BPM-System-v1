"""HUMAN resource allocation strategy."""

from datetime import datetime
from typing import List
from uuid import UUID

from ..interfaces import ResourceRepository
from ..schemas import (
    RequirementResult,
    ExcludedResource,
    HumanResourceEvidence,
    HumanResourceRequirement,
    ExclusionReasonEntry,
)
from ..constants import ResourceType
from ..retrieval import CandidateRetriever
from ..eligibility import EligibilityEvaluator
from ..ranking import HumanResourceRanker
from .base import ResourceStrategy


class HumanResourceStrategy(ResourceStrategy):
    """Strategy for HUMAN resource allocation."""

    def __init__(self, repository: ResourceRepository):
        """Initialize with a resource repository."""
        self.repository = repository
        self.retriever = CandidateRetriever(repository)
        self.ranker = HumanResourceRanker()

    async def process_requirement(
        self,
        requirement: HumanResourceRequirement,
        tenant_id: UUID,
        evaluation_timestamp: datetime,
    ) -> RequirementResult:
        """Process a HUMAN resource requirement.

        Pipeline:
        1. Retrieve candidates (tenant-scoped only)
        2. Evaluate eligibility (hard rules)
        3. Rank eligible resources (deterministic scoring)
        4. Return results
        """
        candidates = await self.retriever.retrieve_human_candidates(
            tenant_id=tenant_id,
            evaluation_timestamp=evaluation_timestamp,
        )
        
        # Step 2: Evaluate eligibility
        evaluator = EligibilityEvaluator(evaluation_timestamp)
        eligible_resources: List[HumanResourceEvidence] = []
        excluded_resources: List[ExcludedResource] = []
        
        for candidate in candidates:
            is_eligible, exclusion_reasons = evaluator.evaluate_eligibility(
                resource=candidate,
                requirement=requirement,
            )
            
            if is_eligible:
                eligible_resources.append(candidate)
            else:
                excluded_resources.append(
                    ExcludedResource(
                        resource_id=candidate.resource_id,
                        resource_type=candidate.resource_type,
                        name=candidate.name,
                        exclusion_reasons=exclusion_reasons,
                    )
                )
        
        # Step 3: Rank eligible resources
        ranked_candidates = self.ranker.rank_candidates(
            eligible_resources=eligible_resources,
            requirement=requirement,
        )
        
        # Step 4: Return results
        return RequirementResult(
            resource_type=ResourceType.HUMAN,
            eligible_candidates=ranked_candidates,
            excluded_resources=excluded_resources,
        )
