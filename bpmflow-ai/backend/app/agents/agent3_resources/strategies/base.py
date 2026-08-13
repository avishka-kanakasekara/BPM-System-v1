"""Base strategy interface for resource allocation."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from ..schemas import (
    RequirementResult,
    ExcludedResource,
    HumanResourceEvidence,
    BudgetResourceEvidence,
    HumanResourceRequirement,
    BudgetResourceRequirement,
)


class ResourceStrategy(ABC):
    """Abstract base class for resource allocation strategies."""

    @abstractmethod
    async def process_requirement(
        self,
        requirement,
        evaluation_timestamp,
    ) -> RequirementResult:
        """Process a resource requirement and return results.
        
        Args:
            requirement: HumanResourceRequirement or BudgetResourceRequirement
            evaluation_timestamp: Fixed timestamp for deterministic behavior
            
        Returns:
            RequirementResult with eligible candidates, exclusions, and validation
        """
        pass
