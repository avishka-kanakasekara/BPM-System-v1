"""Map normalized read-path rows into Agent 3 budget evidence models."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping, Optional
from uuid import UUID

from ...constants import ResourceType
from ...schemas import BudgetResourceEvidence, validate_timezone_aware
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


def map_budget_resource_evidence(
    resource_row: Mapping[str, Any],
    profile_row: Mapping[str, Any],
    evidence_rows: List[Mapping[str, Any]],
    expected_tenant_id: UUID,
) -> BudgetResourceEvidence:
    """Map joined rows into BudgetResourceEvidence."""
    resource_id = _require_uuid(resource_row.get("id"), "resource_id")
    tenant_id = _require_uuid(resource_row.get("tenant_id"), "tenant_id")

    if tenant_id != expected_tenant_id:
        raise CrossTenantGraphError("Resource tenant_id does not match query tenant")

    profile_tenant_id = _require_uuid(profile_row.get("tenant_id"), "profile.tenant_id")
    profile_resource_id = _require_uuid(profile_row.get("resource_id"), "profile.resource_id")
    if profile_tenant_id != tenant_id or profile_resource_id != resource_id:
        raise CrossTenantGraphError("Budget profile does not belong to resource tenant graph")

    for row in evidence_rows:
        row_tenant = _require_uuid(row.get("tenant_id"), "evidence.tenant_id")
        row_resource = _require_uuid(row.get("resource_id"), "evidence.resource_id")
        if row_tenant != tenant_id or row_resource != resource_id:
            raise CrossTenantGraphError("Evidence row crosses tenant/resource boundary")

    if not profile_row:
        raise MissingEvidenceError("BUDGET resource missing budget_resource_profiles row")

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

    return BudgetResourceEvidence(
        resource_id=resource_id,
        tenant_id=tenant_id,
        resource_type=ResourceType.BUDGET,
        name=str(resource_row["name"]),
        available_balance=_require_decimal(
            profile_row["available_balance"], "available_balance"
        ),
        currency=str(profile_row["currency"]),
        cost_centre=profile_row.get("cost_centre"),
        valid_from=_require_aware(profile_row["valid_from"], "valid_from"),
        valid_until=_require_aware(profile_row["valid_until"], "valid_until"),
        authorization_limit=_require_decimal(
            profile_row["authorization_limit"], "authorization_limit"
        ),
        evidence_checked_at=evidence_checked_at,
        evidence_valid_until=evidence_valid_until,
        evidence_references=evidence_references,
    )
