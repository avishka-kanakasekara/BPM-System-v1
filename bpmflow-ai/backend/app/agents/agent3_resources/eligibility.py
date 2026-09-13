"""Hard eligibility validation for Agent 3 Resource Allocation."""

from datetime import datetime
from decimal import Decimal

from .constants import MAX_EVIDENCE_AGE_DAYS, ExclusionReason
from .schemas import (
    ExclusionReasonEntry,
    HumanResourceEvidence,
    HumanResourceRequirement,
)
from .sod_checks import build_sod_exclusion


class EligibilityEvaluator:
    """Evaluates hard eligibility rules for HUMAN resources."""

    def __init__(self, evaluation_timestamp: datetime):
        """Initialize with a fixed evaluation timestamp for deterministic behavior."""
        self.evaluation_timestamp = evaluation_timestamp

    def evaluate_eligibility(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
    ) -> tuple[bool, list[ExclusionReasonEntry]]:
        """Evaluate a resource against requirements.
        
        Returns:
            (is_eligible, exclusion_reasons)
            - is_eligible: True if no hard rules are violated
            - exclusion_reasons: List of all applicable exclusion reasons
        """
        exclusion_reasons: list[ExclusionReasonEntry] = []

        # Collect all applicable exclusion reasons (do not stop after first failure)
        self._check_inactive_resource(resource, exclusion_reasons)
        self._check_required_role(resource, requirement, exclusion_reasons)
        self._check_department(resource, requirement, exclusion_reasons)
        self._check_mandatory_skills(resource, requirement, exclusion_reasons)
        self._check_required_authority(resource, requirement, exclusion_reasons)
        self._check_authority_amount(resource, requirement, exclusion_reasons)
        self._check_availability(resource, requirement, exclusion_reasons)
        self._check_projected_workload(resource, requirement, exclusion_reasons)
        self._check_segregation_of_duties(resource, requirement, exclusion_reasons)
        self._check_requester_self_approval(resource, requirement, exclusion_reasons)
        self._check_conflict_of_interest(resource, exclusion_reasons)
        self._check_missing_evidence(resource, exclusion_reasons)
        self._check_stale_evidence(resource, exclusion_reasons)
        self._check_company_email(resource, exclusion_reasons)

        is_eligible = len(exclusion_reasons) == 0
        return is_eligible, exclusion_reasons

    def _check_inactive_resource(
        self,
        resource: HumanResourceEvidence,
        exclusion_reasons: list[ExclusionReasonEntry],
    ) -> None:
        """Check if resource is inactive."""
        if not resource.is_active:
            reason = (
                ExclusionReason.INACTIVE_EMPLOYEE
                if resource.employee_id is not None
                else ExclusionReason.INACTIVE_RESOURCE
            )
            exclusion_reasons.append(
                ExclusionReasonEntry(
                    reason=reason,
                    description=f"Resource {resource.name} is inactive",
                    evidence_reference="is_active flag",
                )
            )

    def _check_required_role(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
        exclusion_reasons: list[ExclusionReasonEntry],
    ) -> None:
        """Check if resource has any of the required roles."""
        if requirement.required_roles:
            from .directory_bridge import role_tokens

            resource_roles = role_tokens(resource.roles)
            required_roles = role_tokens(requirement.required_roles)
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
        exclusion_reasons: list[ExclusionReasonEntry],
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
        exclusion_reasons: list[ExclusionReasonEntry],
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
        exclusion_reasons: list[ExclusionReasonEntry],
    ) -> None:
        """Check if resource is available before task deadline."""
        if not requirement.availability_required:
            return
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
        exclusion_reasons: list[ExclusionReasonEntry],
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
        exclusion_reasons: list[ExclusionReasonEntry],
    ) -> None:
        """Check for segregation of duties violations."""
        sod_exclusion = build_sod_exclusion(
            resource.segregation_of_duties_conflicts,
            resource_name=resource.name,
        )
        if sod_exclusion is not None:
            exclusion_reasons.append(sod_exclusion)

    def _check_requester_self_approval(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
        exclusion_reasons: list[ExclusionReasonEntry],
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
        if (
            requirement.requester_employee_id is not None
            and resource.employee_id is not None
            and resource.employee_id == requirement.requester_employee_id
        ):
            exclusion_reasons.append(
                ExclusionReasonEntry(
                    reason=ExclusionReason.SAME_PERSON,
                    description="Requester and candidate are the same company employee",
                    evidence_reference="employee_id vs requester_employee_id",
                )
            )

    def _check_conflict_of_interest(
        self,
        resource: HumanResourceEvidence,
        exclusion_reasons: list[ExclusionReasonEntry],
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
        exclusion_reasons: list[ExclusionReasonEntry],
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
        exclusion_reasons: list[ExclusionReasonEntry],
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

    def _check_department(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
        exclusion_reasons: list[ExclusionReasonEntry],
    ) -> None:
        if requirement.required_department_id is not None:
            if resource.department_id != requirement.required_department_id:
                exclusion_reasons.append(
                    ExclusionReasonEntry(
                        reason=ExclusionReason.DEPARTMENT_MISMATCH,
                        description="Candidate department does not match the required department",
                        evidence_reference="department_id",
                    )
                )
                return
        if requirement.required_department_code:
            needed = requirement.required_department_code.strip().upper()
            actual = (resource.department_code or "").strip().upper()
            if actual != needed:
                exclusion_reasons.append(
                    ExclusionReasonEntry(
                        reason=ExclusionReason.DEPARTMENT_MISMATCH,
                        description=f"Candidate department {actual or 'unknown'} does not match {needed}",
                        evidence_reference="department_code",
                    )
                )

    def _check_authority_amount(
        self,
        resource: HumanResourceEvidence,
        requirement: HumanResourceRequirement,
        exclusion_reasons: list[ExclusionReasonEntry],
    ) -> None:
        if requirement.minimum_authority_amount is None:
            return
        if resource.authority_max_amount is None or resource.authority_max_amount < requirement.minimum_authority_amount:
            exclusion_reasons.append(
                ExclusionReasonEntry(
                    reason=ExclusionReason.INSUFFICIENT_AUTHORITY,
                    description=(
                        f"Authority limit {resource.authority_max_amount} is below "
                        f"required {requirement.minimum_authority_amount}"
                    ),
                    evidence_reference="authority_max_amount",
                )
            )
            return
        if requirement.authority_currency:
            have = (resource.authority_currency or "").strip().upper()
            need = requirement.authority_currency.strip().upper()
            if have != need:
                exclusion_reasons.append(
                    ExclusionReasonEntry(
                        reason=ExclusionReason.INSUFFICIENT_AUTHORITY,
                        description=f"Authority currency {have or 'unknown'} does not match {need}",
                        evidence_reference="authority_currency",
                    )
                )
        if requirement.required_authority_code:
            have = (resource.authority or "").strip().upper()
            need = requirement.required_authority_code.strip().upper()
            if have != need:
                exclusion_reasons.append(
                    ExclusionReasonEntry(
                        reason=ExclusionReason.REQUIRED_AUTHORITY_MISSING,
                        description=f"Resource lacks required authority code {need}",
                        evidence_reference="authority",
                    )
                )

    def _check_company_email(
        self,
        resource: HumanResourceEvidence,
        exclusion_reasons: list[ExclusionReasonEntry],
    ) -> None:
        if resource.employee_id is None:
            return
        if not resource.employee_email:
            exclusion_reasons.append(
                ExclusionReasonEntry(
                    reason=ExclusionReason.MISSING_COMPANY_EMAIL,
                    description="Company directory has no verified email for this employee",
                    evidence_reference="employee_email",
                )
            )
