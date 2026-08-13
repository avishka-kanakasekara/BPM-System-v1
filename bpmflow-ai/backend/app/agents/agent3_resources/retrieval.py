"""Candidate discovery for Agent 3 Resource Allocation."""

from typing import List
from uuid import UUID
from datetime import datetime

from .interfaces import ResourceRepository
from .schemas import HumanResourceEvidence, BudgetResourceEvidence
from .constants import ResourceType


class CandidateRetriever:
    """Retrieves candidates filtered only by tenant_id and resource_type."""

    def __init__(self, repository: ResourceRepository):
        """Initialize with a resource repository."""
        self.repository = repository

    async def retrieve_human_candidates(
        self,
        tenant_id: UUID,
        evaluation_timestamp: datetime,
    ) -> List[HumanResourceEvidence]:
        """Retrieve HUMAN resources filtered by tenant_id only.
        
        Cross-tenant resources are never returned.
        No pre-filtering by role, skills, authority, status, workload, or availability.
        Those are evidence inputs for eligibility evaluation.
        """
        resources = await self.repository.get_human_resources_by_tenant(
            tenant_id=tenant_id,
            evaluation_timestamp=evaluation_timestamp,
        )
        
        # Double-verify tenant isolation (defense in depth)
        return [r for r in resources if r.tenant_id == tenant_id]

    async def retrieve_budget_candidates(
        self,
        tenant_id: UUID,
        evaluation_timestamp: datetime,
    ) -> List[BudgetResourceEvidence]:
        """Retrieve BUDGET resources filtered by tenant_id only.
        
        Cross-tenant resources are never returned.
        """
        resources = await self.repository.get_budget_resources_by_tenant(
            tenant_id=tenant_id,
            evaluation_timestamp=evaluation_timestamp,
        )
        
        # Double-verify tenant isolation (defense in depth)
        return [r for r in resources if r.tenant_id == tenant_id]
