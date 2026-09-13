"""HUMAN resource allocation strategy."""

from datetime import datetime
from uuid import UUID

from ..constants import ExclusionReason, GapType, ResourceType
from ..directory_bridge import load_directory_candidates
from ..eligibility import EligibilityEvaluator
from ..interfaces import ResourceRepository
from ..ranking import HumanResourceRanker
from ..retrieval import CandidateRetriever
from ..schemas import (
    ExcludedResource,
    ExclusionReasonEntry,
    HumanResourceEvidence,
    HumanResourceRequirement,
    RequirementResult,
)
from .base import ResourceStrategy


class HumanResourceStrategy(ResourceStrategy):
    """Strategy for HUMAN resource allocation."""

    def __init__(self, repository: ResourceRepository, directory=None):
        """Initialize with a resource repository and optional company directory."""
        self.repository = repository
        self.directory = directory
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
        1. Retrieve candidates (tenant-scoped; directory is identity source when present)
        2. Evaluate eligibility (hard rules)
        3. Rank eligible resources (deterministic scoring)
        4. Return results
        """
        repo_candidates = await self.retriever.retrieve_human_candidates(
            tenant_id=tenant_id,
            evaluation_timestamp=evaluation_timestamp,
        )
        if self.directory is not None:
            candidates = load_directory_candidates(
                self.directory,
                tenant_id=tenant_id,
                evaluation_timestamp=evaluation_timestamp,
                repository_resources=repo_candidates,
            )
        else:
            candidates = [item for item in repo_candidates if item.tenant_id == tenant_id]

        if requirement.assignment_kind == "approver" and self.directory is not None:
            candidates = self._filter_approver_candidates(
                candidates, requirement=requirement, tenant_id=tenant_id
            )

        evaluator = EligibilityEvaluator(evaluation_timestamp)
        eligible_resources: list[HumanResourceEvidence] = []
        excluded_resources: list[ExcludedResource] = []

        for candidate in candidates:
            if candidate.tenant_id != tenant_id:
                excluded_resources.append(
                    ExcludedResource(
                        resource_id=candidate.resource_id,
                        resource_type=candidate.resource_type,
                        name=candidate.name,
                        employee_id=candidate.employee_id,
                        exclusion_reasons=[
                            ExclusionReasonEntry(
                                reason=ExclusionReason.CROSS_TENANT_DENIED,
                                description="Candidate belongs to a different tenant",
                                evidence_reference="tenant_id",
                            )
                        ],
                    )
                )
                continue
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
                        employee_id=candidate.employee_id,
                    )
                )

        ranked_candidates = self.ranker.rank_candidates(
            eligible_resources=eligible_resources,
            requirement=requirement,
        )
        outcome = None
        if not ranked_candidates:
            if requirement.assignment_kind == "approver":
                outcome = GapType.APPROVER_NOT_RESOLVED.value
            else:
                outcome = GapType.NO_ELIGIBLE_RESOURCE.value
        return RequirementResult(
            resource_type=ResourceType.HUMAN,
            eligible_candidates=ranked_candidates,
            excluded_resources=excluded_resources,
            outcome_code=outcome,
        )

    def _filter_approver_candidates(
        self,
        candidates: list[HumanResourceEvidence],
        *,
        requirement: HumanResourceRequirement,
        tenant_id: UUID,
    ) -> list[HumanResourceEvidence]:
        if not requirement.required_approval_type:
            return candidates
        allowed = {
            item.employee_id
            for item in self.directory.resolve_active_approvers(
                tenant_id=tenant_id,
                approval_type=requirement.required_approval_type,
                amount=requirement.minimum_authority_amount,
                currency=requirement.authority_currency,
                department_id=requirement.required_department_id,
                required_authority=requirement.required_authority_code,
            )
        }
        if not allowed:
            return []
        return [item for item in candidates if item.employee_id in allowed]
