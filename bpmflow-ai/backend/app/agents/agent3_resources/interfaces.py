"""Repository interfaces for Agent 3 Resource Allocation."""

from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from .schemas import (
    HumanResourceEvidence,
    BudgetResourceEvidence,
    HumanResourceRequirement,
    BudgetResourceRequirement,
)


class ResourceRepository(ABC):
    """Abstract repository for resource evidence retrieval."""

    @abstractmethod
    async def get_human_resources_by_tenant(
        self,
        tenant_id: UUID,
        evaluation_timestamp: datetime,
    ) -> List[HumanResourceEvidence]:
        """Retrieve all HUMAN resources for a tenant.
        
        Filters only by tenant_id and resource_type.
        Does not pre-filter by role, skills, authority, status, workload, or availability.
        Cross-tenant resources must never be returned.
        """
        pass

    @abstractmethod
    async def get_budget_resources_by_tenant(
        self,
        tenant_id: UUID,
        evaluation_timestamp: datetime,
    ) -> List[BudgetResourceEvidence]:
        """Retrieve all BUDGET resources for a tenant.
        
        Filters only by tenant_id and resource_type.
        Cross-tenant resources must never be returned.
        """
        pass


class InMemoryResourceRepository(ResourceRepository):
    """In-memory implementation for Phase 1 testing."""

    def __init__(self):
        """Initialize with empty storage."""
        self._human_resources: List[HumanResourceEvidence] = []
        self._budget_resources: List[BudgetResourceEvidence] = []

    def add_human_resource(self, resource: HumanResourceEvidence) -> None:
        """Add a HUMAN resource to storage."""
        self._human_resources.append(resource)

    def add_budget_resource(self, resource: BudgetResourceEvidence) -> None:
        """Add a BUDGET resource to storage."""
        self._budget_resources.append(resource)

    async def get_human_resources_by_tenant(
        self,
        tenant_id: UUID,
        evaluation_timestamp: datetime,
    ) -> List[HumanResourceEvidence]:
        """Retrieve HUMAN resources filtered by tenant_id only."""
        return [
            r for r in self._human_resources
            if r.tenant_id == tenant_id and r.resource_type == "HUMAN"
        ]

    async def get_budget_resources_by_tenant(
        self,
        tenant_id: UUID,
        evaluation_timestamp: datetime,
    ) -> List[BudgetResourceEvidence]:
        """Retrieve BUDGET resources filtered by tenant_id only."""
        return [
            r for r in self._budget_resources
            if r.tenant_id == tenant_id and r.resource_type == "BUDGET"
        ]

    def clear(self) -> None:
        """Clear all stored resources (for test isolation)."""
        self._human_resources.clear()
        self._budget_resources.clear()
