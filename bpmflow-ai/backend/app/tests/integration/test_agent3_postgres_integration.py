"""Real PostgreSQL integration tests for Agent 3 read-path repository.

Requires AGENT3_TEST_DATABASE_URL pointing to a dev/test database with
migrations 0002 and 0003 applied. Skipped automatically when unset.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent3_resources.constants import ResourceType
from app.agents.agent3_resources.fixtures import get_requester_id
from app.agents.agent3_resources.repositories.mappers.human_evidence_mapper import (
    map_human_resource_evidence,
)
from app.agents.agent3_resources.repositories.postgres_resource_repository import (
    PostgresResourceRepository,
)
from app.agents.agent3_resources.repositories.seed_constants import (
    AGENT3_DEMO_TENANT_ID,
    AGENT3_OTHER_TENANT_ID,
    BUDGET_INVALID_ID,
    BUDGET_VALID_ID,
    HUMAN_ELIGIBLE_ID,
    HUMAN_INACTIVE_ID,
    HUMAN_MISSING_SKILL_ID,
    HUMAN_OTHER_TENANT_ID,
    HUMAN_SOD_CONFLICT_ID,
    HUMAN_SOD_TARGET_ID,
    HUMAN_UNAVAILABLE_ID,
    HUMAN_WORKLOAD_EXCEEDED_ID,
    SEED_EVALUATION_TIMESTAMP,
)

pytestmark = pytest.mark.integration


@pytest.mark.anyio
class TestAgent3PostgresIntegration:
    """Real PostgreSQL integration tests — not run without AGENT3_TEST_DATABASE_URL."""

    async def test_migration_created_tables_exist(self, verify_agent3_tables):
        assert verify_agent3_tables is None

    async def test_demo_tenant_human_resources_retrieved(
        self,
        postgres_repository: PostgresResourceRepository,
        verify_agent3_tables,
    ):
        results = await postgres_repository.get_human_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        returned_ids = {item.resource_id for item in results}
        assert HUMAN_ELIGIBLE_ID in returned_ids
        assert HUMAN_MISSING_SKILL_ID in returned_ids
        assert HUMAN_WORKLOAD_EXCEEDED_ID in returned_ids
        assert HUMAN_SOD_CONFLICT_ID in returned_ids
        assert HUMAN_INACTIVE_ID in returned_ids

    async def test_human_lookup_returns_human_only(
        self,
        postgres_repository: PostgresResourceRepository,
        verify_agent3_tables,
    ):
        results = await postgres_repository.get_human_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        assert results
        assert all(item.resource_type == ResourceType.HUMAN for item in results)

    async def test_budget_lookup_returns_budget_only(
        self,
        postgres_repository: PostgresResourceRepository,
        verify_agent3_tables,
    ):
        results = await postgres_repository.get_budget_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        assert len(results) == 2
        assert all(item.resource_type == ResourceType.BUDGET for item in results)

    async def test_cross_tenant_resources_invisible(
        self,
        postgres_repository: PostgresResourceRepository,
        verify_agent3_tables,
    ):
        demo_results = await postgres_repository.get_human_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        other_results = await postgres_repository.get_human_resources_by_tenant(
            AGENT3_OTHER_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        demo_ids = {item.resource_id for item in demo_results}
        other_ids = {item.resource_id for item in other_results}
        assert HUMAN_OTHER_TENANT_ID not in demo_ids
        assert HUMAN_ELIGIBLE_ID not in other_ids

    async def test_roles_skills_authorities_mapped(
        self,
        postgres_repository: PostgresResourceRepository,
        verify_agent3_tables,
    ):
        results = await postgres_repository.get_human_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        eligible = next(item for item in results if item.resource_id == HUMAN_ELIGIBLE_ID)
        assert eligible.roles == ["developer"]
        assert eligible.mandatory_skills == ["fastapi", "python"]
        assert eligible.authority == "senior"

    async def test_latest_workload_snapshot_selected(
        self,
        postgres_repository: PostgresResourceRepository,
        verify_agent3_tables,
    ):
        results = await postgres_repository.get_human_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        eligible = next(item for item in results if item.resource_id == HUMAN_ELIGIBLE_ID)
        assert eligible.current_workload_percentage == Decimal("35.00")

    async def test_availability_evidence_mapped(
        self,
        postgres_repository: PostgresResourceRepository,
        verify_agent3_tables,
    ):
        results = await postgres_repository.get_human_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        eligible = next(item for item in results if item.resource_id == HUMAN_ELIGIBLE_ID)
        assert eligible.available_from.tzinfo is not None
        assert eligible.available_from < SEED_EVALUATION_TIMESTAMP
        assert eligible.available_until is None

    async def test_budget_decimal_values_preserved(
        self,
        postgres_repository: PostgresResourceRepository,
        verify_agent3_tables,
    ):
        results = await postgres_repository.get_budget_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        valid = next(item for item in results if item.resource_id == BUDGET_VALID_ID)
        invalid = next(item for item in results if item.resource_id == BUDGET_INVALID_ID)
        assert isinstance(valid.available_balance, Decimal)
        assert valid.available_balance == Decimal("50000.00")
        assert invalid.cost_centre == "CC-INVALID"
        assert invalid.available_balance == Decimal("100.00")

    async def test_evidence_references_returned(
        self,
        postgres_repository: PostgresResourceRepository,
        verify_agent3_tables,
    ):
        humans = await postgres_repository.get_human_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        budgets = await postgres_repository.get_budget_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        eligible = next(item for item in humans if item.resource_id == HUMAN_ELIGIBLE_ID)
        valid_budget = next(item for item in budgets if item.resource_id == BUDGET_VALID_ID)
        assert eligible.evidence_references["hr_profile"]["scenario"] == "eligible"
        assert valid_budget.evidence_references["budget_profile"]["scenario"] == "valid_budget"

    def test_naive_datetimes_rejected_by_mapper(self):
        naive = datetime(2026, 1, 1, 12, 0, 0)
        with pytest.raises(Exception):
            map_human_resource_evidence(
                {
                    "id": HUMAN_ELIGIBLE_ID,
                    "tenant_id": AGENT3_DEMO_TENANT_ID,
                    "name": "Synthetic",
                    "is_active": True,
                },
                expected_tenant_id=AGENT3_DEMO_TENANT_ID,
                roles=["developer"],
                skills=["python"],
                authority="senior",
                availability_row={
                    "tenant_id": AGENT3_DEMO_TENANT_ID,
                    "resource_id": HUMAN_ELIGIBLE_ID,
                    "available_from": naive,
                    "available_until": None,
                },
                workload_row={
                    "tenant_id": AGENT3_DEMO_TENANT_ID,
                    "resource_id": HUMAN_ELIGIBLE_ID,
                    "current_workload_pct": Decimal("35"),
                    "max_workload_pct": Decimal("80"),
                },
                profile_row={
                    "tenant_id": AGENT3_DEMO_TENANT_ID,
                    "resource_id": HUMAN_ELIGIBLE_ID,
                    "max_workload_pct": Decimal("80"),
                    "evidence_checked_at": SEED_EVALUATION_TIMESTAMP,
                    "evidence_valid_until": SEED_EVALUATION_TIMESTAMP,
                },
                sod_conflicts=[],
                coi_flags=[],
                evidence_rows=[],
            )

    async def test_missing_required_avidence_excluded_from_results(
        self,
        postgres_repository: PostgresResourceRepository,
        verify_agent3_tables,
    ):
        results = await postgres_repository.get_human_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        returned_ids = {item.resource_id for item in results}
        assert HUMAN_UNAVAILABLE_ID not in returned_ids

    async def test_sod_conflict_mapped(
        self,
        postgres_repository: PostgresResourceRepository,
        verify_agent3_tables,
    ):
        results = await postgres_repository.get_human_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        conflicted = next(item for item in results if item.resource_id == HUMAN_SOD_CONFLICT_ID)
        assert HUMAN_SOD_TARGET_ID in conflicted.segregation_of_duties_conflicts

    async def test_stable_resource_ordering(
        self,
        postgres_repository: PostgresResourceRepository,
        verify_agent3_tables,
    ):
        results = await postgres_repository.get_human_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        ids = [item.resource_id for item in results]
        assert ids == sorted(ids)

    async def test_requester_id_not_used_as_tenant_filter(
        self,
        postgres_repository: PostgresResourceRepository,
        verify_agent3_tables,
    ):
        requester_id = get_requester_id()
        results = await postgres_repository.get_human_resources_by_tenant(
            AGENT3_DEMO_TENANT_ID,
            SEED_EVALUATION_TIMESTAMP,
        )
        assert all(item.tenant_id == AGENT3_DEMO_TENANT_ID for item in results)
        assert requester_id != AGENT3_DEMO_TENANT_ID
