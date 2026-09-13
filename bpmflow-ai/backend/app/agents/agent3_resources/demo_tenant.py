"""In-memory demo tenant matching Agent 3 synthetic seed data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from .constants import ResourceType
from .interfaces import InMemoryResourceRepository
from .repositories.seed_constants import (
    AGENT3_DEMO_TENANT_ID,
    AGENT3_OTHER_TENANT_ID,
    BUDGET_INVALID_ID,
    BUDGET_IT_ID,
    BUDGET_VALID_ID,
    HUMAN_BUYER_ID,
    HUMAN_ELIGIBLE_ID,
    HUMAN_INACTIVE_ID,
    HUMAN_MANAGER_ID,
    HUMAN_MISSING_SKILL_ID,
    HUMAN_OTHER_TENANT_ID,
    HUMAN_SOD_CONFLICT_ID,
    HUMAN_SOD_TARGET_ID,
    HUMAN_UNAVAILABLE_ID,
    HUMAN_WORKLOAD_EXCEEDED_ID,
    SEED_EVALUATION_TIMESTAMP,
    SEED_EVIDENCE_CHECKED_AT,
    SEED_EVIDENCE_VALID_UNTIL,
)
from .schemas import BudgetResourceEvidence, HumanResourceEvidence


def _evidence(scenario: str) -> dict:
    return {
        "availability": {"verified_at": SEED_EVIDENCE_CHECKED_AT.isoformat()},
        "workload": {"verified_at": SEED_EVIDENCE_CHECKED_AT.isoformat()},
        "hr_profile": {"source": "agent3_demo_tenant", "scenario": scenario},
    }


def _human(
    *,
    resource_id: UUID,
    name: str,
    scenario: str,
    roles: list[str],
    skills: list[str],
    authority: str,
    current_workload: Decimal,
    max_workload: Decimal = Decimal("80"),
    is_active: bool = True,
    available_from: datetime | None = None,
    sod_conflicts: list[UUID] | None = None,
) -> HumanResourceEvidence:
    available_from = available_from or SEED_EVALUATION_TIMESTAMP - timedelta(days=30)
    return HumanResourceEvidence(
        resource_id=resource_id,
        tenant_id=AGENT3_DEMO_TENANT_ID,
        resource_type=ResourceType.HUMAN,
        name=name,
        is_active=is_active,
        roles=roles,
        mandatory_skills=skills,
        preferred_skills=[],
        authority=authority,
        available_from=available_from,
        available_until=None,
        current_workload_percentage=current_workload,
        max_workload_percentage=max_workload,
        projected_workload_percentage=current_workload,
        segregation_of_duties_conflicts=sod_conflicts or [],
        conflict_of_interest_flags=[],
        evidence_checked_at=SEED_EVIDENCE_CHECKED_AT,
        evidence_valid_until=SEED_EVIDENCE_VALID_UNTIL,
        evidence_references=_evidence(scenario),
    )


def build_demo_human_resources() -> list[HumanResourceEvidence]:
    """Return all demo-tenant HUMAN profiles used by G3 tests."""
    return [
        _human(
            resource_id=HUMAN_ELIGIBLE_ID,
            name="Synthetic Employee Alpha",
            scenario="eligible",
            roles=["developer"],
            skills=["python", "fastapi"],
            authority="senior",
            current_workload=Decimal("35"),
        ),
        _human(
            resource_id=HUMAN_MISSING_SKILL_ID,
            name="Synthetic Employee Beta",
            scenario="missing_skill",
            roles=["developer"],
            skills=["python"],
            authority="senior",
            current_workload=Decimal("40"),
        ),
        _human(
            resource_id=HUMAN_UNAVAILABLE_ID,
            name="Synthetic Employee Gamma",
            scenario="unavailable",
            roles=["developer"],
            skills=["python", "fastapi"],
            authority="senior",
            current_workload=Decimal("30"),
            available_from=datetime(2026, 6, 1, tzinfo=UTC),
        ),
        _human(
            resource_id=HUMAN_WORKLOAD_EXCEEDED_ID,
            name="Synthetic Employee Delta",
            scenario="workload_exceeded",
            roles=["developer"],
            skills=["python", "fastapi"],
            authority="senior",
            current_workload=Decimal("88"),
            max_workload=Decimal("90"),
        ),
        _human(
            resource_id=HUMAN_SOD_CONFLICT_ID,
            name="Synthetic Employee Epsilon",
            scenario="sod_conflict",
            roles=["developer"],
            skills=["python", "fastapi"],
            authority="senior",
            current_workload=Decimal("45"),
            sod_conflicts=[HUMAN_SOD_TARGET_ID],
        ),
        _human(
            resource_id=HUMAN_INACTIVE_ID,
            name="Synthetic Employee Zeta",
            scenario="inactive",
            roles=["developer"],
            skills=["python", "fastapi"],
            authority="senior",
            current_workload=Decimal("20"),
            is_active=False,
        ),
        _human(
            resource_id=HUMAN_SOD_TARGET_ID,
            name="Synthetic Employee Sod Target",
            scenario="sod_target",
            roles=["approver"],
            skills=["python"],
            authority="senior",
            current_workload=Decimal("25"),
        ),
        _human(
            resource_id=HUMAN_BUYER_ID,
            name="Synthetic Employee Buyer",
            scenario="buyer",
            roles=["developer", "buyer"],
            skills=["python"],
            authority="senior",
            current_workload=Decimal("25"),
        ),
        _human(
            resource_id=HUMAN_MANAGER_ID,
            name="Synthetic Employee Manager",
            scenario="manager",
            roles=["developer", "manager"],
            skills=["python", "fastapi"],
            authority="standard",
            current_workload=Decimal("30"),
        ),
    ]


def build_demo_budget_resources() -> list[BudgetResourceEvidence]:
    """Return demo-tenant BUDGET profiles."""
    common = {
        "tenant_id": AGENT3_DEMO_TENANT_ID,
        "resource_type": ResourceType.BUDGET,
        "valid_from": datetime(2025, 1, 1, tzinfo=UTC),
        "valid_until": datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
        "evidence_checked_at": SEED_EVIDENCE_CHECKED_AT,
        "evidence_valid_until": SEED_EVIDENCE_VALID_UNTIL,
    }
    return [
        BudgetResourceEvidence(
            resource_id=BUDGET_VALID_ID,
            name="Synthetic Budget Valid",
            available_balance=Decimal("50000"),
            currency="USD",
            cost_centre="CC-DEMO",
            authorization_limit=Decimal("25000"),
            evidence_references={
                "budget_profile": {"source": "agent3_demo_tenant", "scenario": "valid_budget"}
            },
            **common,
        ),
        BudgetResourceEvidence(
            resource_id=BUDGET_INVALID_ID,
            name="Synthetic Budget Invalid",
            available_balance=Decimal("100"),
            currency="USD",
            cost_centre="CC-INVALID",
            authorization_limit=Decimal("50"),
            evidence_references={
                "budget_profile": {"source": "agent3_demo_tenant", "scenario": "invalid_budget"}
            },
            **common,
        ),
        BudgetResourceEvidence(
            resource_id=BUDGET_IT_ID,
            name="Synthetic Budget IT",
            available_balance=Decimal("120000"),
            currency="USD",
            cost_centre="CC-IT-100",
            authorization_limit=Decimal("60000"),
            evidence_references={
                "budget_profile": {"source": "agent3_demo_tenant", "scenario": "it_budget"}
            },
            **common,
        ),
    ]


def build_demo_tenant_repository(
    *,
    include_other_tenant: bool = True,
) -> InMemoryResourceRepository:
    """Populate an in-memory repository with the coherent demo tenant."""
    repository = InMemoryResourceRepository()
    for resource in build_demo_human_resources():
        repository.add_human_resource(resource)
    for budget in build_demo_budget_resources():
        repository.add_budget_resource(budget)
    if include_other_tenant:
        repository.add_human_resource(
            _human(
                resource_id=HUMAN_OTHER_TENANT_ID,
                name="Synthetic Employee Other Tenant",
                scenario="other_tenant",
                roles=["developer"],
                skills=["python"],
                authority="senior",
                current_workload=Decimal("20"),
            ).model_copy(update={"tenant_id": AGENT3_OTHER_TENANT_ID})
        )
    return repository
