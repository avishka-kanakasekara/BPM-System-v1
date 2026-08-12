"""Synthetic test fixtures for Agent 3 Resource Allocation."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List
from uuid import UUID, uuid4

from .schemas import (
    HumanResourceEvidence,
    BudgetResourceEvidence,
    HumanResourceRequirement,
    BudgetResourceRequirement,
)
from .constants import ResourceType


def create_human_evidence(
    tenant_id: UUID,
    resource_id: UUID = None,
    name: str = "Test Employee",
    is_active: bool = True,
    roles: List[str] = None,
    mandatory_skills: List[str] = None,
    preferred_skills: List[str] = None,
    authority: str = None,
    current_workload: Decimal = Decimal("50"),
    max_workload: Decimal = Decimal("100"),
    sod_conflicts: List[UUID] = None,
    coi_flags: List[str] = None,
    evidence_age_days: int = 30,
) -> HumanResourceEvidence:
    """Create a synthetic HUMAN resource evidence."""
    now = datetime.now(timezone.utc)
    return HumanResourceEvidence(
        resource_id=resource_id or uuid4(),
        tenant_id=tenant_id,
        resource_type=ResourceType.HUMAN,
        name=name,
        is_active=is_active,
        roles=roles or [],
        mandatory_skills=mandatory_skills or [],
        preferred_skills=preferred_skills or [],
        authority=authority,
        available_from=now - timedelta(days=1),
        available_until=now + timedelta(days=365),
        current_workload_percentage=current_workload,
        max_workload_percentage=max_workload,
        projected_workload_percentage=current_workload,
        segregation_of_duties_conflicts=sod_conflicts or [],
        conflict_of_interest_flags=coi_flags or [],
        evidence_checked_at=now - timedelta(days=evidence_age_days),
        evidence_valid_until=now + timedelta(days=90),
        evidence_references={
            "source": "synthetic_fixture",
            "availability": {"verified_at": now.isoformat()},
            "workload": {"verified_at": now.isoformat()},
        },
    )


def create_budget_evidence(
    tenant_id: UUID,
    resource_id: UUID = None,
    name: str = "Test Budget",
    available_balance: Decimal = Decimal("10000"),
    currency: str = "USD",
    cost_centre: str = "CC001",
    authorization_limit: Decimal = Decimal("50000"),
    evidence_age_days: int = 30,
) -> BudgetResourceEvidence:
    """Create a synthetic BUDGET resource evidence."""
    now = datetime.now(timezone.utc)
    return BudgetResourceEvidence(
        resource_id=resource_id or uuid4(),
        tenant_id=tenant_id,
        resource_type=ResourceType.BUDGET,
        name=name,
        available_balance=available_balance,
        currency=currency,
        cost_centre=cost_centre,
        valid_from=now - timedelta(days=30),
        valid_until=now + timedelta(days=365),
        authorization_limit=authorization_limit,
        evidence_checked_at=now - timedelta(days=evidence_age_days),
        evidence_valid_until=now + timedelta(days=90),
        evidence_references={"source": "synthetic_fixture"},
    )


def create_human_requirement(
    tenant_id: UUID,
    requester_id: UUID = None,
    required_roles: List[str] = None,
    mandatory_skills: List[str] = None,
    preferred_skills: List[str] = None,
    required_authority: str = None,
    estimated_effort: Decimal = Decimal("40"),
    deadline_days: int = 30,
) -> HumanResourceRequirement:
    """Create a synthetic HUMAN resource requirement."""
    now = datetime.now(timezone.utc)
    return HumanResourceRequirement(
        resource_type=ResourceType.HUMAN,
        required_roles=required_roles or [],
        mandatory_skills=mandatory_skills or [],
        preferred_skills=preferred_skills or [],
        required_authority=required_authority,
        requester_id=requester_id or uuid4(),
        task_deadline=now + timedelta(days=deadline_days),
        estimated_effort_hours=estimated_effort,
        process_stage="resource_allocation",
    )


def create_budget_requirement(
    tenant_id: UUID,
    requester_id: UUID = None,
    required_amount: Decimal = Decimal("5000"),
    currency: str = "USD",
    cost_centre: str = "CC001",
    deadline_days: int = 30,
) -> BudgetResourceRequirement:
    """Create a synthetic BUDGET resource requirement."""
    now = datetime.now(timezone.utc)
    return BudgetResourceRequirement(
        resource_type=ResourceType.BUDGET,
        required_amount=required_amount,
        currency=currency,
        cost_centre=cost_centre,
        requester_id=requester_id or uuid4(),
        task_deadline=now + timedelta(days=deadline_days),
        process_stage="resource_allocation",
    )


# Pre-defined test scenarios
def get_tenant_a_id() -> UUID:
    """Fixed tenant ID for consistent testing."""
    return UUID("00000000-0000-0000-0000-000000000001")


def get_tenant_b_id() -> UUID:
    """Fixed tenant ID for cross-tenant isolation testing."""
    return UUID("00000000-0000-0000-0000-000000000002")


def get_requester_id() -> UUID:
    """Fixed requester ID for self-approval testing."""
    return UUID("00000000-0000-0000-0000-000000000003")


def get_resource_id_1() -> UUID:
    """Fixed resource ID for deterministic testing."""
    return UUID("00000000-0000-0000-0000-000000000010")


def get_resource_id_2() -> UUID:
    """Fixed resource ID for deterministic testing."""
    return UUID("00000000-0000-0000-0000-000000000011")


def get_resource_id_3() -> UUID:
    """Fixed resource ID for deterministic testing."""
    return UUID("00000000-0000-0000-0000-000000000012")
