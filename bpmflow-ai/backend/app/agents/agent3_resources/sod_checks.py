"""Pure segregation-of-duties (SoD) checks for Agent 3."""

from __future__ import annotations

from uuid import UUID

from .constants import ExclusionReason
from .schemas import ExclusionReasonEntry


def has_sod_conflict(conflicts: list[UUID]) -> bool:
    """Return True when the resource has one or more SoD conflicts."""
    return bool(conflicts)


def build_sod_exclusion(
    conflicts: list[UUID],
    *,
    resource_name: str = "Resource",
) -> ExclusionReasonEntry | None:
    """Build an exclusion entry when SoD conflicts are present."""
    if not has_sod_conflict(conflicts):
        return None
    return ExclusionReasonEntry(
        reason=ExclusionReason.SEGREGATION_OF_DUTIES_VIOLATION,
        description=(
            f"{resource_name} has {len(conflicts)} segregation-of-duties conflict(s)"
        ),
        evidence_reference="segregation_of_duties_conflicts",
    )
