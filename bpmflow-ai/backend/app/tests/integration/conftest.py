"""Shared fixtures for Agent 3 PostgreSQL integration tests."""

from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlparse

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agents.agent3_resources.repositories.postgres_resource_repository import (
    PostgresResourceRepository,
)
from app.agents.agent3_resources.repositories.session_factory import (
    create_async_session_factory,
    create_postgres_resource_repository,
)

AGENT3_TEST_DATABASE_URL_ENV = "AGENT3_TEST_DATABASE_URL"


def _resolve_test_database_url() -> Optional[str]:
    return os.getenv(AGENT3_TEST_DATABASE_URL_ENV)


def _is_safe_test_database_url(database_url: str) -> bool:
    """Reject obvious production hosts; integration tests require explicit test URL."""
    parsed = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    blocked_markers = ("prod", "production", "live")
    return not any(marker in host for marker in blocked_markers)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: Agent 3 PostgreSQL integration tests requiring AGENT3_TEST_DATABASE_URL",
    )


@pytest.fixture(scope="session")
def agent3_test_database_url() -> str:
    database_url = _resolve_test_database_url()
    if not database_url:
        pytest.skip(
            f"{AGENT3_TEST_DATABASE_URL_ENV} is not configured; "
            "integration tests skipped"
        )
    if not _is_safe_test_database_url(database_url):
        pytest.skip(
            f"{AGENT3_TEST_DATABASE_URL_ENV} host looks non-dev/test; "
            "integration tests skipped for safety"
        )
    return database_url


@pytest.fixture
async def agent3_test_engine(agent3_test_database_url: str):
    engine, _factory = create_async_session_factory(agent3_test_database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def agent3_session_factory(agent3_test_database_url: str):
    _engine, factory = create_async_session_factory(agent3_test_database_url)
    try:
        yield factory
    finally:
        await _engine.dispose()


@pytest.fixture
def postgres_repository(
    agent3_session_factory,
) -> PostgresResourceRepository:
    return create_postgres_resource_repository(agent3_session_factory)


@pytest.fixture
async def verify_agent3_tables(agent3_test_engine: AsyncEngine) -> None:
    required_tables = (
        "tenants",
        "resources",
        "roles",
        "skills",
        "authorities",
        "human_resource_profiles",
        "budget_resource_profiles",
        "resource_availability",
        "workload_snapshots",
        "evidence_references",
        "sod_rules",
        "resource_declared_conflicts",
    )
    async with agent3_test_engine.connect() as connection:
        result = await connection.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(:tables)
                """
            ),
            {"tables": list(required_tables)},
        )
        found = {row[0] for row in result.fetchall()}
    missing = set(required_tables) - found
    if missing:
        pytest.skip(
            "Agent 3 read-path tables missing; apply migrations 0002 and 0003 first: "
            + ", ".join(sorted(missing))
        )
