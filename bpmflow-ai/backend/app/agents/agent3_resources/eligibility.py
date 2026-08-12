"""Hard eligibility validation for Agent 3 Resource Allocation."""

from datetime import datetime
from decimal import Decimal
from typing import List, Set
from uuid import UUID

from .schemas import (
    HumanResourceEvidence,
    HumanResourceRequirement,
    ExcludedResource,
    ExclusionReasonEntry,
)
from .constants import ExclusionReason, MAX_EVIDENCE_AGE_DAYS


class EligibilityEvaluator:
    """Evaluates hard eligibility rules for HUMAN resources."""

    def __init__(self, evaluation_timestamp: datetime):
        """Initialize with a fixed evaluation timestamp for deterministic behavior."""
        self.evaluation_timestamp = evaluation_timestamp

    def evaluate_eligibility(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
    ) -> tuple[bool, List[ExclusionReasonEntry]]:
        """Evaluate a resource against requirements.
        
        Returns:
            (is_eligible, exclusion_reasons)
            - is_eligible: True if no hard rules are violated
            - exclusion_reasons: List of all applicable exclusion reasons
        """
        exclusion_reasons: List[ExclusionReasonEntry] = []

        # Collect all applicable exclusion reasons (do not stop after first failure)
        self._check_inactive_resource(resource, exclusion_reasons)
        self._check_required_role(resource, requirement, exclusion_reasons)
        self._check_mandatory_skills(resource, requirement, exclusion_reasons)
        self._check_required_authority(resource, requirement, exclusion_reasons)
        self._check_availability(resource, requirement, exclusion_reasons)
        self._check_projected_workload(resource, requirement, exclusion_reasons)
        self._check_segregation_of_duties(resource, requirement, exclusion_reasons)
        self._check_requester_self_approval(resource, requirement, exclusion_reasons)
        self._check_conflict_of_interest(resource, exclusion_reasons)
        self._check_missing_evidence(resource, exclusion_reasons)
        self._check_stale_evidence(resource, exclusion_reasons)

        is_eligible = len(exclusion_reasons) == 0
        return is_eligible, exclusion_reasons

    def _check_inactive_resource(
        self,
        resource: HumanResourceEvidence,
        exclusion_reasons: List[ExclusionReasonEntry],
    ) -> None:
        """Check if resource is inactive."""
        if not resource.is_active:
            exclusion_reasons.append(
                ExclusionReasonEntry(
                    reason=ExclusionReason.INACTIVE_RESOURCE,
                    description=f"Resource {resource.name} is inactive",
                    evidence_reference="is_active flag",
                )
            )

    def _check_required_role(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
        exclusion_reasons: List[ExclusionReasonEntry],
    ) -> None:
        """Check if resource has any of the required roles."""
        if requirement.required_roles:
            resource_roles = set(resource.roles)
            required_roles = set(requirement.required_roles)
            if not resource_roles.intersection(required_roles):
                exclusion_reasons.append(
                    ExclusionReasonEntry(
                        reason=ExclusionReason.REQUIRED_ROLE_MISSING,
                        description=f"Resource lacks required roles. Has: {resource.roles}, Required: {requirement.required_roles}",
                        evidence_reference="roles field",
                    )
                )

    def _check_mandatory_skills(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
        exclusion_reasons: List[ExclusionReasonEntry],
    ) -> None:
        """Check if resource has all mandatory skills."""
        if requirement.mandatory_skills:
            resource_skills = set(resource.mandatory_skills)
            mandatory_skills = set(requirement.mandatory_skills)
            missing_skills = mandatory_skills - resource_skills
            if missing_skills:
                exclusion_reasons.append(
                    ExclusionReasonEntry(
                        reason=ExclusionReason.MANDATORY_SKILL_MISSING,
                        description=f"Resource lacks mandatory skills. Missing: {sorted(missing_skills)}",
                        evidence_reference="mandatory_skills field",
                    )
                )

    def _check_required_authority(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
        exclusion_reasons: List[ExclusionReasonEntry],
    ) -> None:
        """Check if resource has required authority."""
        if requirement.required_authority:
            if resource.authority != requirement.required_authority:
                exclusion_reasons.append(
                    ExclusionReasonEntry(
                        reason=ExclusionReason.REQUIRED_AUTHORITY_MISSING,
                        description=f"Resource lacks required authority. Has: {resource.authority}, Required: {requirement.required_authority}",
                        evidence_reference="authority field",
                    )
                )

    def _check_availability(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
        exclusion_reasons: List[ExclusionReasonEntry],
    ) -> None:
        """Check if resource is available before task deadline."""
        if resource.available_from > requirement.task_deadline:
            exclusion_reasons.append(
                ExclusionReasonEntry(
                    reason=ExclusionReason.UNAVAILABLE_BEFORE_DEADLINE,
                    description=f"Resource not available until {resource.available_from}, but task deadline is {requirement.task_deadline}",
                    evidence_reference="available_from and task_deadline",
                )
            )

    def _check_projected_workload(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
        exclusion_reasons: List[ExclusionReasonEntry],
    ) -> None:
        """Check if projected workload exceeds maximum.
        
        projected_workload_percentage = current_workload_percentage + requested_effort_percentage
        """
        # Convert effort hours to percentage (assume 40-hour work week = 100%)
        # For simplicity, use a fixed conversion: 1 hour = 2.5% of weekly capacity
        effort_percentage = requirement.estimated_effort_hours * Decimal("2.5")
        projected = resource.current_workload_percentage + effort_percentage
        
        if projected > resource.max_workload_percentage:
            exclusion_reasons.append(
                ExclusionReasonEntry(
                    reason=ExclusionReason.PROJECTED_WORKLOAD_EXCEEDED,
                    description=f"Projected workload {projected}% exceeds maximum {resource.max_workload_percentage}%",
                    evidence_reference="current_workload_percentage and estimated_effort_hours",
                )
            )

    def _check_segregation_of_duties(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
        exclusion_reasons: List[ExclusionReasonEntry],
    ) -> None:
        """Check for segregation of duties violations."""
        if resource.segregation_of_duties_conflicts:
            exclusion_reasons.append(
                ExclusionReasonEntry(
                    reason=ExclusionReason.SEGREGATION_OF_DUTIES_VIOLATION,
                    description=f"Resource has {len(resource.segregation_of_duties_conflicts)} segregation of duties conflicts",
                    evidence_reference="segregation_of_duties_conflicts",
                )
            )

    def _check_requester_self_approval(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
        exclusion_reasons: List[ExclusionReasonEntry],
    ) -> None:
        """Check if requester is trying to approve themselves."""
        if resource.resource_id == requirement.requester_id:
            exclusion_reasons.append(
                ExclusionReasonEntry(
                    reason=ExclusionReason.REQUESTER_SELF_APPROVAL,
                    description="Requester cannot approve their own allocation",
                    evidence_reference="resource_id vs requester_id",
                )
            )

    def _check_conflict_of_interest(
        self,
        resource: HumanResourceEvidence,
        exclusion_reasons: List[ExclusionReasonEntry],
    ) -> None:
        """Check for conflict of interest flags."""
        if resource.conflict_of_interest_flags:
            exclusion_reasons.append(
                ExclusionReasonEntry(
                    reason=ExclusionReason.CONFLICT_OF_INTEREST,
                    description=f"Resource has conflict of interest flags: {resource.conflict_of_interest_flags}",
                    evidence_reference="conflict_of_interest_flags",
                )
            )

    def _check_missing_evidence(
        self,
        resource: HumanResourceEvidence,
        exclusion_reasons: List[ExclusionReasonEntry],
    ) -> None:
        """Check if required availability and workload evidence is missing."""
        missing_fields = []
        if not resource.evidence_references:
            missing_fields.append("evidence_references")
        else:
            if "availability" not in resource.evidence_references:
                missing_fields.append("availability_evidence")
            if "workload" not in resource.evidence_references:
                missing_fields.append("workload_evidence")

        if missing_fields:
            exclusion_reasons.append(
                ExclusionReasonEntry(
                    reason=ExclusionReason.MISSING_REQUIRED_EVIDENCE,
                    description=f"Missing required evidence fields: {missing_fields}",
                    evidence_reference="evidence_references",
                )
            )

    def _check_stale_evidence(
        self,
        resource: HumanResourceEvidence,
        exclusion_reasons: List[ExclusionReasonEntry],
    ) -> None:
        """Check if evidence is stale (older than MAX_EVIDENCE_AGE_DAYS)."""
        evidence_age = (self.evaluation_timestamp - resource.evidence_checked_at).days
        
        if evidence_age > MAX_EVIDENCE_AGE_DAYS:
            exclusion_reasons.append(
                ExclusionReasonEntry(
                    reason=ExclusionReason.STALE_EVIDENCE,
                    description=f"Evidence is {evidence_age} days old, maximum allowed is {MAX_EVIDENCE_AGE_DAYS} days",
                    evidence_reference="evidence_checked_at",
                )
            )
