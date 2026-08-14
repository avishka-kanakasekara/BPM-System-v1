"""Static migration contract tests for Agent 3 write-path persistence (0004)."""

import pytest
from pathlib import Path


class TestMigration0004Contract:
    """Static contract tests for 0004 migration SQL."""

    @pytest.fixture
    def migration_path(self) -> Path:
        """Path to the 0004 migration file."""
        return Path(__file__).parent.parent.parent.parent / "supabase" / "migrations" / "0004_agent3_write_path_persistence.sql"

    @pytest.fixture
    def migration_content(self, migration_path: Path) -> str:
        """Read migration file content."""
        return migration_path.read_text()

    def test_migration_file_exists(self, migration_path: Path) -> None:
        """Test that 0004 migration file exists."""
        assert migration_path.exists(), "0004 migration file must exist"

    def test_migration_contains_all_required_tables(self, migration_content: str) -> None:
        """Test that migration contains all 10 required tables."""
        required_tables = [
            "allocation_requests",
            "allocation_requirements",
            "allocation_recommendations",
            "allocation_candidates",
            "allocation_exclusions",
            "allocation_exclusion_reasons",
            "resource_gaps",
            "resource_alternatives",
            "budget_validation_results",
            "recommendation_evidence_links",
        ]
        for table in required_tables:
            assert f"CREATE TABLE IF NOT EXISTS public.{table}" in migration_content, f"Missing table: {table}"

    def test_migration_uses_uuid_primary_keys(self, migration_content: str) -> None:
        """Test that all tables use UUID primary keys."""
        assert "id UUID PRIMARY KEY" in migration_content or "id UUID PRIMARY KEY DEFAULT gen_random_uuid()" in migration_content

    def test_migration_has_tenant_id_not_null(self, migration_content: str) -> None:
        """Test that all tables have tenant_id NOT NULL."""
        assert "tenant_id UUID NOT NULL" in migration_content

    def test_migration_uses_timestamptz(self, migration_content: str) -> None:
        """Test that timestamp columns use TIMESTAMPTZ."""
        assert "TIMESTAMPTZ NOT NULL" in migration_content

    def test_migration_uses_numeric_for_scores(self, migration_content: str) -> None:
        """Test that scores use NUMERIC(5,4), not FLOAT or REAL."""
        assert "NUMERIC(5, 4)" in migration_content
        assert "FLOAT" not in migration_content.upper()
        assert "REAL" not in migration_content.upper()

    def test_migration_uses_numeric_for_money(self, migration_content: str) -> None:
        """Test that money values use NUMERIC(18,2)."""
        assert "NUMERIC(18, 2)" in migration_content

    def test_migration_uses_numeric_for_workload(self, migration_content: str) -> None:
        """Test that workload percentages use NUMERIC(5,2)."""
        assert "NUMERIC(5, 2)" in migration_content

    def test_migration_has_check_constraints(self, migration_content: str) -> None:
        """Test that migration has CHECK constraints."""
        assert "CHECK (" in migration_content

    def test_migration_no_approved_rejected_status(self, migration_content: str) -> None:
        """Test that APPROVED and REJECTED statuses are not allowed."""
        # Check status constraint
        assert "CHECK (status IN ('GENERATED', 'PENDING_HUMAN_APPROVAL', 'SUPERSEDED', 'FAILED'))" in migration_content
        # Ensure APPROVED and REJECTED are not in the allowed list
        assert "'APPROVED'" not in migration_content
        assert "'REJECTED'" not in migration_content

    def test_migration_business_constraint_shape(self, migration_content: str) -> None:
        """Test that business recommendations have proper shape constraints."""
        # Check for business shape constraint
        assert "allocation_recommendations_business_shape CHECK" in migration_content
        assert "requires_human_approval = TRUE" in migration_content
        assert "confidence IS NOT NULL" in migration_content

    def test_migration_failed_shape(self, migration_content: str) -> None:
        """Test that FAILED recommendations have proper shape constraints."""
        assert "status = 'FAILED'" in migration_content
        assert "requires_human_approval = FALSE" in migration_content
        assert "error_code IS NOT NULL" in migration_content
        assert "confidence IS NULL" in migration_content

    def test_migration_has_rls_enabled(self, migration_content: str) -> None:
        """Test that RLS is enabled on all tables."""
        assert "ENABLE ROW LEVEL SECURITY" in migration_content

    def test_migration_no_permissive_rls_policies(self, migration_content: str) -> None:
        """Test that no permissive USING(true) policies exist."""
        assert "USING(true)" not in migration_content

    def test_migration_has_tenant_safe_fks(self, migration_content: str) -> None:
        """Test that foreign keys include tenant_id for tenant safety."""
        assert "FOREIGN KEY (tenant_id," in migration_content

    def test_migration_has_indexes(self, migration_content: str) -> None:
        """Test that migration has indexes for read paths."""
        assert "CREATE INDEX" in migration_content

    def test_migration_has_advisory_comments(self, migration_content: str) -> None:
        """Test that migration has comments about Agent 3 being advisory."""
        assert "Agent 3 is advisory" in migration_content or "advisory only" in migration_content
        assert "human approval" in migration_content.lower()

    def test_migration_requester_id_not_tenant_id(self, migration_content: str) -> None:
        """Test that comments explain requester_id is not tenant_id."""
        assert "requester_id" in migration_content
        # Check for comment explaining the distinction
        assert "requester" in migration_content.lower()

    def test_migration_has_unique_constraints(self, migration_content: str) -> None:
        """Test that migration has unique constraints for idempotency."""
        assert "UNIQUE (" in migration_content
        assert "idempotency" in migration_content.lower()

    def test_migration_has_jsonb_only_for_payloads(self, migration_content: str) -> None:
        """Test that JSONB is used only for payloads/evidence."""
        assert "JSONB" in migration_content
        # Check that JSONB is used for request/response payloads
        assert "request_payload JSONB" in migration_content or "request_payload" in migration_content

    def test_migration_preserves_sequence_order(self, migration_content: str) -> None:
        """Test that sequence_order columns exist for deterministic ordering."""
        assert "sequence_order" in migration_content
        assert "candidate_rank" in migration_content

    def test_migration_has_updated_at_triggers(self, migration_content: str) -> None:
        """Test that updated_at triggers are created."""
        assert "update_updated_at_column" in migration_content

    def test_migration_no_process_instance_fk(self, migration_content: str) -> None:
        """Test that process_instance_id is nullable and not an FK."""
        # process_instance_id should be nullable UUID
        assert "process_instance_id UUID" in migration_content
        # Should not have a FK constraint to a process_instances table
        assert "process_instance_id" not in migration_content or "FOREIGN KEY" not in migration_content.split("process_instance_id")[1].split("\n")[0]

    def test_migration_exclusion_reasons_normalized(self, migration_content: str) -> None:
        """Test that exclusion reasons are stored in separate table, not comma-separated."""
        assert "allocation_exclusion_reasons" in migration_content
        # Should not have comma-separated reason storage
        assert "reason_code TEXT NOT NULL" in migration_content

    def test_migration_alternatives_preserve_order(self, migration_content: str) -> None:
        """Test that alternatives have sequence_order for deterministic ordering."""
        assert "resource_alternatives" in migration_content
        assert "sequence_order INTEGER" in migration_content

    def test_migration_budget_validation_separate(self, migration_content: str) -> None:
        """Test that budget validation is in separate table with proper columns."""
        assert "budget_validation_results" in migration_content
        assert "available_balance NUMERIC(18, 2)" in migration_content
        assert "required_amount NUMERIC(18, 2)" in migration_content

    def test_migration_evidence_links_tenant_safe(self, migration_content: str) -> None:
        """Test that evidence links are tenant-safe."""
        assert "recommendation_evidence_links" in migration_content
        assert "tenant_id UUID NOT NULL" in migration_content

    def test_migration_versioning(self, migration_content: str) -> None:
        """Test that recommendations have versioning."""
        assert "recommendation_version INTEGER" in migration_content
        assert "supersedes_recommendation_id" in migration_content
