"""Shared test fixtures for Agent 3 tests."""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from app.agents.agent3_resources import (
    InMemoryResourceRepository,
    create_human_evidence,
    create_budget_evidence,
    create_human_requirement,
    create_budget_requirement,
    get_tenant_a_id,
    get_tenant_b_id,
    get_requester_id,
    get_resource_id_1,
    get_resource_id_2,
    get_resource_id_3,
)
from app.agents.agent3_resources.fixtures import FIXTURE_REFERENCE_TIMESTAMP

UTC = timezone.utc


def utc_datetime(*args, **kwargs) -> datetime:
    """Build a timezone-aware UTC datetime for tests."""
    return datetime(*args, **kwargs, tzinfo=UTC)


@pytest.fixture
def tenant_a_id():
    """Fixed tenant ID for testing."""
    return get_tenant_a_id()


@pytest.fixture
def tenant_b_id():
    """Fixed tenant ID for cross-tenant testing."""
    return get_tenant_b_id()


@pytest.fixture
def requester_id():
    """Fixed requester ID for testing."""
    return get_requester_id()


@pytest.fixture
def evaluation_timestamp():
    """Fixed evaluation timestamp for deterministic behavior."""
    return FIXTURE_REFERENCE_TIMESTAMP


@pytest.fixture
def repository():
    """In-memory repository for testing."""
    repo = InMemoryResourceRepository()
    yield repo
    repo.clear()  # Clean up after each test


@pytest.fixture
def populated_repository(tenant_a_id, repository, evaluation_timestamp):
    """Repository populated with test data."""
    repository.add_human_resource(
        create_human_evidence(
            tenant_id=tenant_a_id,
            reference_timestamp=evaluation_timestamp,
            resource_id=get_resource_id_1(),
            name="Active Employee",
            is_active=True,
            roles=["developer"],
            mandatory_skills=["python"],
            preferred_skills=["fastapi"],
            authority="senior",
            current_workload=Decimal("50"),
            max_workload=Decimal("100"),
        )
    )

    repository.add_human_resource(
        create_human_evidence(
            tenant_id=tenant_a_id,
            reference_timestamp=evaluation_timestamp,
            resource_id=get_resource_id_2(),
            name="Inactive Employee",
            is_active=False,
            roles=["developer"],
            mandatory_skills=["python"],
            current_workload=Decimal("30"),
            max_workload=Decimal("100"),
        )
    )

    repository.add_budget_resource(
        create_budget_evidence(
            tenant_id=tenant_a_id,
            reference_timestamp=evaluation_timestamp,
            name="Team Budget",
            available_balance=Decimal("10000"),
            currency="USD",
            cost_centre="CC001",
        )
    )

    return repository
