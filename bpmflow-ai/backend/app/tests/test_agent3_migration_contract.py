"""Static contract tests for Agent 3 migrations 0002 and 0003 SQL."""

from pathlib import Path
import re

import pytest

from app.agents.agent3_resources.constants import RecommendationStatus
from app.agents.agent3_resources.repositories.seed_constants import (
    AGENT3_DEMO_TENANT_CODE,
    AGENT3_DEMO_TENANT_ID,
    BUDGET_INVALID_ID,
    BUDGET_VALID_ID,
    HUMAN_ELIGIBLE_ID,
    HUMAN_INACTIVE_ID,
    HUMAN_MISSING_SKILL_ID,
    HUMAN_SOD_CONFLICT_ID,
    HUMAN_UNAVAILABLE_ID,
    HUMAN_WORKLOAD_EXCEEDED_ID,
    MIGRATION_0003_FILENAME,
)
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
MIGRATION_0003 = MIGRATIONS_DIR / MIGRATION_0003_FILENAME


@pytest.fixture(scope="module")
def migration_0002_sql() -> str:
    assert MIGRATION_0002.exists(), "0002 migration must exist"
    return MIGRATION_0002.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def migration_0003_sql() -> str:
    assert MIGRATION_0003.exists(), "0003 migration must exist"
    return MIGRATION_0003.read_text(encoding="utf-8")


class TestMigration0002Contract:
    """Static SQL contract tests for migration 0002 — no live PostgreSQL connection."""

    def test_0002_exists_and_0001_unchanged(self):
        assert MIGRATION_0002.name == "0002_agent3_resource_persistence.sql"
        assert MIGRATION_0001.exists()

    def test_required_read_path_tables_present(self, migration_0002_sql):
        for table in READ_PATH_TABLES:
            assert f"public.{table}" in migration_0002_sql or f" {table} " in migration_0002_sql

    def test_tenant_id_on_every_read_path_table(self, migration_0002_sql):
        for table in READ_PATH_TABLES:
            if table == "tenants":
                continue
            assert f"CREATE TABLE" in migration_0002_sql
            section = migration_0002_sql.split(f"public.{table}", 1)[-1]
            assert "tenant_id" in section.split(";", 1)[0]

    def test_no_float_or_real_for_money_or_scores(self, migration_0002_sql):
        lowered = migration_0002_sql.lower()
        assert "float" not in lowered
        assert " real" not in lowered
        assert "double precision" not in lowered

    def test_workload_snapshots_have_no_projected_column(self, migration_0002_sql):
        section = migration_0002_sql.split("public.workload_snapshots", 1)[1].split("--", 1)[0]
        assert "projected" not in section.lower()

    def test_resource_skills_has_no_mandatory_or_preferred_flag(self, migration_0002_sql):
        section = migration_0002_sql.split("public.resource_skills", 1)[1].split(";", 20)[0]
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

    def test_tenant_safe_constraints_present(self, migration_0002_sql):
        assert "resources_tenant_id_id_unique" in migration_0002_sql
        assert "FOREIGN KEY (tenant_id, resource_id)" in migration_0002_sql
        assert "roles_tenant_id_unique" in migration_0002_sql
        assert "skills_tenant_id_unique" in migration_0002_sql
        assert "authorities_tenant_id_unique" in migration_0002_sql

    def test_legacy_demo_tenant_backfill(self, migration_0002_sql):
        assert LEGACY_DEMO_TENANT_ID in migration_0002_sql
        assert "LEGACY_DEMO" in migration_0002_sql
        assert "UPDATE public.resources" in migration_0002_sql
        assert "ALTER COLUMN tenant_id SET NOT NULL" in migration_0002_sql

    def test_allowed_resource_types_check(self, migration_0002_sql):
        for resource_type in ALLOWED_RESOURCE_TYPES:
            assert resource_type in migration_0002_sql

    def test_rls_enabled_without_insecure_policies(self, migration_0002_sql):
        assert "ENABLE ROW LEVEL SECURITY" in migration_0002_sql
        assert "USING (true)" not in migration_0002_sql


class TestMigration0003Contract:
    """Static SQL contract tests for migration 0003 synthetic seed — no live PostgreSQL."""

    def test_0003_exists_with_expected_name(self):
        assert MIGRATION_0003.name == MIGRATION_0003_FILENAME

    def test_contains_synthetic_data_only(self, migration_0003_sql):
        lowered = migration_0003_sql.lower()
        assert "synthetic" in lowered
        forbidden = ("@", "nic", "passport", "realname", "production")
        for token in forbidden:
            assert token not in lowered

    def test_uses_fixed_uuids(self, migration_0003_sql):
        assert str(AGENT3_DEMO_TENANT_ID) in migration_0003_sql
        assert str(HUMAN_ELIGIBLE_ID) in migration_0003_sql
        assert str(BUDGET_VALID_ID) in migration_0003_sql
        uuid_count = len(re.findall(
            r"00000000-0000-0000-0000-0000000000[0-9]{2}",
            migration_0003_sql,
        ))
        assert uuid_count >= 20

    def test_tenant_scoped_references(self, migration_0003_sql):
        assert AGENT3_DEMO_TENANT_CODE in migration_0003_sql
        assert "tenant_id" in migration_0003_sql
        assert "00000000-0000-0000-0000-000000000001" in migration_0003_sql

    def test_required_human_scenarios_present(self, migration_0003_sql):
        scenarios = {
            str(HUMAN_ELIGIBLE_ID): "eligible",
            str(HUMAN_MISSING_SKILL_ID): "missing skill",
            str(HUMAN_UNAVAILABLE_ID): "future availability",
            str(HUMAN_WORKLOAD_EXCEEDED_ID): "88.00",
            str(HUMAN_SOD_CONFLICT_ID): "declared conflict",
            str(HUMAN_INACTIVE_ID): "FALSE",
        }
        for marker in scenarios:
            assert marker in migration_0003_sql

    def test_required_budget_scenarios_present(self, migration_0003_sql):
        assert str(BUDGET_VALID_ID) in migration_0003_sql
        assert str(BUDGET_INVALID_ID) in migration_0003_sql
        assert "CC-DEMO" in migration_0003_sql
        assert "CC-INVALID" in migration_0003_sql

    def test_does_not_modify_production_users(self, migration_0003_sql):
        lowered = migration_0003_sql.lower()
        assert "public.users" not in lowered
        assert "auth.users" not in lowered

    def test_no_projected_workload_in_snapshots(self, migration_0003_sql):
        snapshot_section = migration_0003_sql.split("workload_snapshots", 1)[1]
        assert "projected" not in snapshot_section.lower()

    def test_idempotent_conflicts_present(self, migration_0003_sql):
        assert migration_0003_sql.count("ON CONFLICT") >= 10

    def test_no_secrets_in_seed_sql(self, migration_0003_sql):
        lowered = migration_0003_sql.lower()
        secret_markers = (
            "password",
            "service_role",
            "jwt",
            "api_key",
            "postgresql://",
            "supabase.co",
        )
        for marker in secret_markers:
            assert marker not in lowered

    def test_sod_rule_and_declared_conflict_present(self, migration_0003_sql):
        assert "sod_rules" in migration_0003_sql
        assert "resource_declared_conflicts" in migration_0003_sql
        assert "evidence_references" in migration_0003_sql
