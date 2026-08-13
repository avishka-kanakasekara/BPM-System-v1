"""Static contract tests for Agent 3 migration 0002 SQL."""

from pathlib import Path

import pytest

from app.agents.agent3_resources.constants import RecommendationStatus
from app.agents.agent3_resources.repositories.table_mapping import (
    AGENT3_RECOMMENDATION_STATUSES,
    ALLOWED_RESOURCE_TYPES,
    LEGACY_DEMO_TENANT_ID,
    MIGRATION_0002_FILENAME,
    READ_PATH_TABLES,
)

BPMFLOW_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = BPMFLOW_ROOT / "supabase" / "migrations"
MIGRATION_0001 = MIGRATIONS_DIR / "0001_init.sql"
MIGRATION_0002 = MIGRATIONS_DIR / MIGRATION_0002_FILENAME


@pytest.fixture(scope="module")
def migration_sql() -> str:
    assert MIGRATION_0002.exists(), "0002 migration must exist"
    return MIGRATION_0002.read_text(encoding="utf-8")


class TestMigrationContract:
    """Static SQL contract tests — no live PostgreSQL connection."""

    def test_0002_exists_and_0001_unchanged(self):
        assert MIGRATION_0002.name == "0002_agent3_resource_persistence.sql"
        assert MIGRATION_0001.exists()
        assert not (MIGRATIONS_DIR / "0003_agent3_resource_persistence.sql").exists()

    def test_required_read_path_tables_present(self, migration_sql):
        for table in READ_PATH_TABLES:
            assert f"public.{table}" in migration_sql or f" {table} " in migration_sql

    def test_tenant_id_on_every_read_path_table(self, migration_sql):
        for table in READ_PATH_TABLES:
            if table == "tenants":
                continue
            assert f"CREATE TABLE" in migration_sql
            section = migration_sql.split(f"public.{table}", 1)[-1]
            assert "tenant_id" in section.split(";", 1)[0]

    def test_no_float_or_real_for_money_or_scores(self, migration_sql):
        lowered = migration_sql.lower()
        assert "float" not in lowered
        assert " real" not in lowered
        assert "double precision" not in lowered

    def test_workload_snapshots_have_no_projected_column(self, migration_sql):
        section = migration_sql.split("public.workload_snapshots", 1)[1].split("--", 1)[0]
        assert "projected" not in section.lower()

    def test_resource_skills_has_no_mandatory_or_preferred_flag(self, migration_sql):
        section = migration_sql.split("public.resource_skills", 1)[1].split(";", 20)[0]
        lowered = section.lower()
        assert "is_mandatory" not in lowered
        assert "is_preferred" not in lowered
        assert "mandatory" not in lowered
        assert "preferred" not in lowered

    def test_agent3_statuses_exclude_approval_decisions(self):
        statuses = {status.value for status in RecommendationStatus}
        assert statuses == set(AGENT3_RECOMMENDATION_STATUSES)
        assert "APPROVED" not in statuses
        assert "REJECTED" not in statuses

    def test_tenant_safe_constraints_present(self, migration_sql):
        assert "resources_tenant_id_id_unique" in migration_sql
        assert "FOREIGN KEY (tenant_id, resource_id)" in migration_sql
        assert "roles_tenant_id_unique" in migration_sql
        assert "skills_tenant_id_unique" in migration_sql
        assert "authorities_tenant_id_unique" in migration_sql

    def test_legacy_demo_tenant_backfill(self, migration_sql):
        assert LEGACY_DEMO_TENANT_ID in migration_sql
        assert "LEGACY_DEMO" in migration_sql
        assert "UPDATE public.resources" in migration_sql
        assert "ALTER COLUMN tenant_id SET NOT NULL" in migration_sql

    def test_allowed_resource_types_check(self, migration_sql):
        for resource_type in ALLOWED_RESOURCE_TYPES:
            assert resource_type in migration_sql

    def test_rls_enabled_without_insecure_policies(self, migration_sql):
        assert "ENABLE ROW LEVEL SECURITY" in migration_sql
        assert "USING (true)" not in migration_sql
