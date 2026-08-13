"""Map normalized read-path rows into Agent 3 human evidence models."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping, Optional
from uuid import UUID

from ...constants import ResourceType
from ...schemas import HumanResourceEvidence, validate_timezone_aware
from ..exceptions import CrossTenantGraphError, MissingEvidenceError, MappingError


def _require_uuid(value: Any, field_name: str) -> UUID:
    if value is None:
        raise MappingError(f"Missing {field_name}")
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _require_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise MappingError(f"{field_name} must be timezone-aware")
    return validate_timezone_aware(value, field_name)


def _require_decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise MappingError(f"Invalid decimal for {field_name}") from exc


def _assert_tenant(resource_id: UUID, tenant_id: UUID, row: Mapping[str, Any], label: str) -> None:
    row_tenant = _require_uuid(row.get("tenant_id"), f"{label}.tenant_id")
    row_resource = _require_uuid(row.get("resource_id"), f"{label}.resource_id")
    if row_tenant != tenant_id or row_resource != resource_id:
        raise CrossTenantGraphError(f"{label} crosses tenant/resource boundary")


def map_human_resource_evidence(
    resource_row: Mapping[str, Any],
    *,
    expected_tenant_id: UUID,
    roles: List[str],
    skills: List[str],
    authority: Optional[str],
    availability_row: Optional[Mapping[str, Any]],
    workload_row: Optional[Mapping[str, Any]],
    profile_row: Mapping[str, Any],
    sod_conflicts: List[UUID],
    coi_flags: List[str],
    evidence_rows: List[Mapping[str, Any]],
) -> HumanResourceEvidence:
    """Map joined rows into HumanResourceEvidence."""
    resource_id = _require_uuid(resource_row.get("id"), "resource_id")
    tenant_id = _require_uuid(resource_row.get("tenant_id"), "tenant_id")

    if tenant_id != expected_tenant_id:
        raise CrossTenantGraphError("Resource tenant_id does not match query tenant")

    if not profile_row:
        raise MissingEvidenceError("HUMAN resource missing human_resource_profiles row")

    _assert_tenant(resource_id, tenant_id, profile_row, "human_profile")

    if availability_row is not None:
        _assert_tenant(resource_id, tenant_id, availability_row, "availability")

    if workload_row is not None:
        _assert_tenant(resource_id, tenant_id, workload_row, "workload")

    for row in evidence_rows:
        _assert_tenant(resource_id, tenant_id, row, "evidence")

    if availability_row is None:
        raise MissingEvidenceError("HUMAN resource missing active availability window")

    if workload_row is None:
        raise MissingEvidenceError("HUMAN resource missing workload snapshot")

    current_workload = _require_decimal(
        workload_row["current_workload_pct"], "current_workload_pct"
    )
    max_workload = _require_decimal(workload_row["max_workload_pct"], "max_workload_pct")
    profile_max = _require_decimal(profile_row["max_workload_pct"], "max_workload_pct")

    if current_workload < 0 or current_workload > 100:
        raise MappingError("current_workload_pct out of range")
    if max_workload < 0 or max_workload > 100 or profile_max < 0 or profile_max > 100:
        raise MappingError("max_workload_pct out of range")

    evidence_references: Dict[str, Any] = {}
    evidence_checked_at: Optional[datetime] = None
    evidence_valid_until: Optional[datetime] = None

    for row in evidence_rows:
        key = row.get("evidence_key")
        if not key:
            raise MappingError("Evidence row missing evidence_key")
        payload = row.get("payload") or {}
        evidence_references[str(key)] = payload
        checked_at = _require_aware(row["checked_at"], "checked_at")
        valid_until = _require_aware(row["valid_until"], "valid_until")
        if evidence_checked_at is None or checked_at < evidence_checked_at:
            evidence_checked_at = checked_at
        if evidence_valid_until is None or valid_until > evidence_valid_until:
            evidence_valid_until = valid_until

    if evidence_checked_at is None:
        evidence_checked_at = _require_aware(
            profile_row["evidence_checked_at"], "evidence_checked_at"
        )
    if evidence_valid_until is None:
        evidence_valid_until = _require_aware(
            profile_row["evidence_valid_until"], "evidence_valid_until"
        )

    available_from = _require_aware(availability_row["available_from"], "available_from")
    available_until_raw = availability_row.get("available_until")
    available_until = (
        _require_aware(available_until_raw, "available_until")
        if available_until_raw is not None
        else None
    )

    return HumanResourceEvidence(
        resource_id=resource_id,
        tenant_id=tenant_id,
        resource_type=ResourceType.HUMAN,
        name=str(resource_row["name"]),
        is_active=bool(resource_row.get("is_active", True)),
        roles=sorted(set(roles)),
        mandatory_skills=sorted(set(skills)),
        preferred_skills=[],
        authority=authority,
        available_from=available_from,
        available_until=available_until,
        current_workload_percentage=current_workload,
        max_workload_percentage=max(profile_max, max_workload),
        projected_workload_percentage=current_workload,
        segregation_of_duties_conflicts=sod_conflicts,
        conflict_of_interest_flags=sorted(set(coi_flags)),
        evidence_checked_at=evidence_checked_at,
        evidence_valid_until=evidence_valid_until,
        evidence_references=evidence_references,
    )
