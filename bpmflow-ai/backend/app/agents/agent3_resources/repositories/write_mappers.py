"""Domain ↔ Database mapping for Agent 3 write-path persistence."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from ..schemas import (
    AllocationRequest,
    AllocationRecommendation,
    HumanResourceRequirement,
    BudgetResourceRequirement,
    RequirementResult,
    RankedCandidate,
    ExcludedResource,
    ExclusionReasonEntry,
    ResourceGap,
    ResourceAlternative,
    BudgetValidationChecks,
    AgentMessageMetadata,
    RecommendationStatus,
    ResourceType,
    GapAlternativeType,
    GapType,
)
from ..constants import SCHEMA_VERSION
from .persistence_exceptions import PersistenceValidationError


def validate_timezone_aware(value: datetime, field_name: str) -> datetime:
    """Ensure a datetime is timezone-aware (UTC-compatible)."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise PersistenceValidationError(f"{field_name} must be timezone-aware (UTC)")
    return value


def generate_idempotency_key(request: AllocationRequest) -> str:
    """Generate a deterministic idempotency key from request metadata."""
    # Use correlation_id + tenant_id + message hash for idempotency
    return f"{request.metadata.correlation_id}_{request.metadata.tenant_id}"


def map_request_to_allocation_request(
    request: AllocationRequest,
    evaluation_timestamp: datetime,
) -> Dict[str, Any]:
    """Map AllocationRequest to allocation_requests table row."""
    validate_timezone_aware(evaluation_timestamp, "evaluation_timestamp")
    
    return {
        "id": uuid4(),
        "tenant_id": request.metadata.tenant_id,
        "idempotency_key": generate_idempotency_key(request),
        "correlation_id": request.metadata.correlation_id,
        "requester_id": request.metadata.tenant_id,  # Use tenant_id as requester for now
        "evaluation_timestamp": evaluation_timestamp,
        "process_instance_id": request.metadata.process_instance_id,
        "task_id": request.metadata.task_id,
        "request_payload": request.model_dump(mode="json"),
        "request_schema_version": SCHEMA_VERSION,
    }


def map_requirement_to_allocation_requirement(
    requirement: HumanResourceRequirement | BudgetResourceRequirement,
    request_id: UUID,
    tenant_id: UUID,
    sequence_order: int,
) -> Dict[str, Any]:
    """Map requirement to allocation_requirements table row."""
    validate_timezone_aware(requirement.task_deadline, "task_deadline")
    
    return {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "request_id": request_id,
        "resource_type": requirement.resource_type.value,
        "sequence_order": sequence_order,
        "requester_id": requirement.requester_id,
        "task_deadline": requirement.task_deadline,
        "process_stage": requirement.process_stage,
        "estimated_effort_hours": getattr(requirement, "estimated_effort_hours", None),
        "requirement_payload": requirement.model_dump(mode="json"),
    }


def map_recommendation_to_allocation_recommendation(
    recommendation: AllocationRecommendation,
    request_id: UUID,
    tenant_id: UUID,
    recommendation_version: int,
    supersedes_recommendation_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Map AllocationRecommendation to allocation_recommendations table row."""
    # Validate status is allowed
    if recommendation.status not in (
        RecommendationStatus.GENERATED,
        RecommendationStatus.PENDING_HUMAN_APPROVAL,
        RecommendationStatus.SUPERSEDED,
        RecommendationStatus.FAILED,
    ):
        raise PersistenceValidationError(
            f"Invalid recommendation status: {recommendation.status}"
        )
    
    # Validate business constraint shape
    if recommendation.status in (
        RecommendationStatus.GENERATED,
        RecommendationStatus.PENDING_HUMAN_APPROVAL,
        RecommendationStatus.SUPERSEDED,
    ):
        if not recommendation.requires_human_approval:
            raise PersistenceValidationError(
                "Business recommendations must require human approval"
            )
        if recommendation.manual_intervention_required:
            raise PersistenceValidationError(
                "Business recommendations should not require manual intervention"
            )
        if not recommendation.explanation or not recommendation.explanation.strip():
            raise PersistenceValidationError(
                "Business recommendations must have non-empty explanation"
            )
        if recommendation.confidence is None:
            raise PersistenceValidationError(
                "Business recommendations must have confidence"
            )
        if recommendation.error_code or recommendation.error_message:
            raise PersistenceValidationError(
                "Business recommendations should not have error fields"
            )
    
    # Validate FAILED shape
    if recommendation.status == RecommendationStatus.FAILED:
        if recommendation.requires_human_approval:
            raise PersistenceValidationError(
                "FAILED recommendations should not require human approval"
            )
        if not recommendation.manual_intervention_required:
            raise PersistenceValidationError(
                "FAILED recommendations must require manual intervention"
            )
        if not recommendation.error_code or not recommendation.error_code.strip():
            raise PersistenceValidationError(
                "FAILED recommendations must have error_code"
            )
        if not recommendation.error_message or not recommendation.error_message.strip():
            raise PersistenceValidationError(
                "FAILED recommendations must have error_message"
            )
        if recommendation.retryable is None:
            raise PersistenceValidationError(
                "FAILED recommendations must have retryable flag"
            )
        if recommendation.confidence is not None:
            raise PersistenceValidationError(
                "FAILED recommendations should not have confidence"
            )
    
    return {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "request_id": request_id,
        "correlation_id": recommendation.metadata.correlation_id,
        "recommendation_version": recommendation_version,
        "status": recommendation.status.value,
        "requires_human_approval": recommendation.requires_human_approval,
        "manual_intervention_required": recommendation.manual_intervention_required,
        "explanation": recommendation.explanation or "",
        "confidence": recommendation.confidence,
        "error_code": recommendation.error_code,
        "error_message": recommendation.error_message,
        "retryable": recommendation.retryable,
        "limitations": recommendation.limitations or [],
        "supersedes_recommendation_id": supersedes_recommendation_id,
        "response_schema_version": SCHEMA_VERSION,
    }


def map_candidate_to_allocation_candidate(
    candidate: RankedCandidate,
    recommendation_id: UUID,
    request_id: UUID,
    requirement_id: UUID,
    tenant_id: UUID,
    candidate_rank: int,
) -> Dict[str, Any]:
    """Map RankedCandidate to allocation_candidates table row."""
    if candidate.available_from:
        validate_timezone_aware(candidate.available_from, "available_from")
    if candidate.available_until:
        validate_timezone_aware(candidate.available_until, "available_until")
    
    return {
        "tenant_id": tenant_id,
        "recommendation_id": recommendation_id,
        "request_id": request_id,
        "requirement_id": requirement_id,
        "resource_id": candidate.resource_id,
        "candidate_rank": candidate_rank,
        "allocation_score": candidate.allocation_score,
        "role_match": candidate.score_breakdown.role_match,
        "skill_match": candidate.score_breakdown.skill_match,
        "availability_score": candidate.score_breakdown.availability_score,
        "workload_fit": candidate.score_breakdown.workload_fit,
        "authority_match": candidate.score_breakdown.authority_match,
        "current_workload_pct": candidate.current_workload_percentage,
        "projected_workload_pct": candidate.projected_workload_percentage,
        "available_from": candidate.available_from,
        "available_until": candidate.available_until,
        "candidate_name": candidate.name,
    }


def map_exclusion_to_allocation_exclusion(
    excluded: ExcludedResource,
    recommendation_id: UUID,
    request_id: UUID,
    requirement_id: UUID,
    tenant_id: UUID,
) -> Dict[str, Any]:
    """Map ExcludedResource to allocation_exclusions table row."""
    return {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "recommendation_id": recommendation_id,
        "request_id": request_id,
        "requirement_id": requirement_id,
        "resource_id": excluded.resource_id,
        "resource_type": excluded.resource_type.value,
    }


def map_exclusion_reason_to_allocation_exclusion_reason(
    reason: ExclusionReasonEntry,
    exclusion_id: UUID,
    tenant_id: UUID,
    sequence_order: int,
) -> Dict[str, Any]:
    """Map ExclusionReasonEntry to allocation_exclusion_reasons table row."""
    return {
        "tenant_id": tenant_id,
        "exclusion_id": exclusion_id,
        "sequence_order": sequence_order,
        "reason_code": reason.reason.value,
        "description": reason.description,
        "evidence_reference": reason.evidence_reference,
    }


def map_gap_to_resource_gap(
    gap: ResourceGap,
    recommendation_id: UUID,
    request_id: UUID,
    tenant_id: UUID,
    requirement_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Map ResourceGap to resource_gaps table row."""
    return {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "recommendation_id": recommendation_id,
        "request_id": request_id,
        "requirement_id": requirement_id,
        "gap_type": gap.gap_type.value,
        "resource_type": gap.resource_type.value,
        "gap_description": gap.gap_description,
        "eligible_count": gap.eligible_count,
        "excluded_count": gap.excluded_count,
    }


def map_alternative_to_resource_alternative(
    alternative: ResourceAlternative,
    gap_id: UUID,
    recommendation_id: UUID,
    tenant_id: UUID,
    sequence_order: int,
) -> Dict[str, Any]:
    """Map ResourceAlternative to resource_alternatives table row."""
    return {
        "tenant_id": tenant_id,
        "gap_id": gap_id,
        "recommendation_id": recommendation_id,
        "sequence_order": sequence_order,
        "alternative_type": alternative.alternative_type.value,
        "description": alternative.description,
        "requires_approval": alternative.requires_approval,
        "estimated_effort_hours": alternative.estimated_effort_hours,
        "cost_impact": alternative.cost_impact,
    }


def map_budget_validation_to_budget_validation_result(
    validation: BudgetValidationChecks,
    recommendation_id: UUID,
    request_id: UUID,
    requirement_id: UUID,
    tenant_id: UUID,
    resource_id: UUID,
) -> Dict[str, Any]:
    """Map BudgetValidationChecks to budget_validation_results table row."""
    return {
        "tenant_id": tenant_id,
        "recommendation_id": recommendation_id,
        "request_id": request_id,
        "requirement_id": requirement_id,
        "resource_id": resource_id,
        "sufficient_balance": validation.sufficient_balance,
        "cost_centre_match": validation.cost_centre_match,
        "currency_match": validation.currency_match,
        "validity_period_valid": validation.validity_period_valid,
        "within_authorization_limit": validation.within_authorization_limit,
        "available_balance": validation.available_balance,
        "required_amount": validation.required_amount,
        "validation_payload": validation.model_dump(mode="json"),
    }


def map_evidence_link_to_recommendation_evidence_link(
    evidence_key: str,
    evidence_reference_id: Optional[UUID],
    resource_id: Optional[UUID],
    link_type: str,
    recommendation_id: UUID,
    tenant_id: UUID,
    sequence_order: int,
) -> Dict[str, Any]:
    """Map evidence reference to recommendation_evidence_links table row."""
    return {
        "tenant_id": tenant_id,
        "recommendation_id": recommendation_id,
        "resource_id": resource_id,
        "evidence_reference_id": evidence_reference_id,
        "evidence_key": evidence_key,
        "link_type": link_type,
        "sequence_order": sequence_order,
    }


# ============================================================================
# Read-back mapping (Database → Domain)
# ============================================================================

def map_row_to_recommendation_header(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map database row to recommendation header dictionary."""
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "request_id": row["request_id"],
        "correlation_id": row["correlation_id"],
        "recommendation_version": row["recommendation_version"],
        "status": row["status"],
        "requires_human_approval": row["requires_human_approval"],
        "manual_intervention_required": row["manual_intervention_required"],
        "explanation": row["explanation"],
        "confidence": Decimal(str(row["confidence"])) if row["confidence"] is not None else None,
        "error_code": row["error_code"],
        "error_message": row["error_message"],
        "retryable": row["retryable"],
        "limitations": row["limitations"],
        "response_schema_version": row["response_schema_version"],
        "created_at": row["created_at"],
    }


def map_row_to_request_metadata(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map database row to request metadata dictionary."""
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "correlation_id": row["correlation_id"],
        "requester_id": row["requester_id"],
        "evaluation_timestamp": row["evaluation_timestamp"],
        "process_instance_id": row["process_instance_id"],
        "task_id": row["task_id"],
        "request_schema_version": row["request_schema_version"],
    }


def map_row_to_candidate(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map database row to candidate dictionary."""
    return {
        "requirement_id": row["requirement_id"],
        "resource_id": row["resource_id"],
        "candidate_rank": row["candidate_rank"],
        "allocation_score": Decimal(str(row["allocation_score"])),
        "role_match": Decimal(str(row["role_match"])),
        "skill_match": Decimal(str(row["skill_match"])),
        "availability_score": Decimal(str(row["availability_score"])),
        "workload_fit": Decimal(str(row["workload_fit"])),
        "authority_match": Decimal(str(row["authority_match"])),
        "current_workload_pct": Decimal(str(row["current_workload_pct"])),
        "projected_workload_pct": Decimal(str(row["projected_workload_pct"])),
        "available_from": row["available_from"],
        "available_until": row["available_until"],
        "candidate_name": row["candidate_name"],
    }


def map_row_to_exclusion_with_reasons(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Map database rows to exclusion with reasons dictionary."""
    if not rows:
        return {}
    
    first_row = rows[0]
    reasons = [
        {
            "sequence_order": r["sequence_order"],
            "reason_code": r["reason_code"],
            "description": r["description"],
            "evidence_reference": r["evidence_reference"],
        }
        for r in rows
    ]
    
    return {
        "id": first_row["id"],
        "requirement_id": first_row["requirement_id"],
        "resource_id": first_row["resource_id"],
        "resource_type": first_row["resource_type"],
        "reasons": reasons,
    }


def map_row_to_gap(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map database row to gap dictionary."""
    return {
        "id": row["id"],
        "requirement_id": row["requirement_id"],
        "gap_type": row["gap_type"],
        "resource_type": row["resource_type"],
        "gap_description": row["gap_description"],
        "eligible_count": row["eligible_count"],
        "excluded_count": row["excluded_count"],
    }


def map_row_to_alternative(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map database row to alternative dictionary."""
    return {
        "gap_id": row["gap_id"],
        "sequence_order": row["sequence_order"],
        "alternative_type": row["alternative_type"],
        "description": row["description"],
        "requires_approval": row["requires_approval"],
        "estimated_effort_hours": Decimal(str(row["estimated_effort_hours"])) if row["estimated_effort_hours"] is not None else None,
        "cost_impact": Decimal(str(row["cost_impact"])) if row["cost_impact"] is not None else None,
    }


def map_row_to_budget_validation(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map database row to budget validation dictionary."""
    return {
        "requirement_id": row["requirement_id"],
        "resource_id": row["resource_id"],
        "sufficient_balance": row["sufficient_balance"],
        "cost_centre_match": row["cost_centre_match"],
        "currency_match": row["currency_match"],
        "validity_period_valid": row["validity_period_valid"],
        "within_authorization_limit": row["within_authorization_limit"],
        "available_balance": Decimal(str(row["available_balance"])),
        "required_amount": Decimal(str(row["required_amount"])),
        "validation_payload": row["validation_payload"],
    }


def map_row_to_evidence_link(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map database row to evidence link dictionary."""
    return {
        "resource_id": row["resource_id"],
        "evidence_key": row["evidence_key"],
        "link_type": row["link_type"],
        "sequence_order": row["sequence_order"],
    }
