"""Deterministic, idempotent SQL migration runner."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

MIGRATION_FILES: Sequence[str] = (
    "0001_init.sql",
    "0002_agent1_discovery.sql",
    "0003_agent4_workflow.sql",
    "0004_agent3_resource_persistence.sql",
    "0005_agent3_synthetic_seed.sql",
    "0006_agent3_write_path_persistence.sql",
    "0007_agent2_execution.sql",
    "0008_company_policy_knowledge.sql",
    "0009_admin_role_provisioning_notes.sql",
    "0010_agent2_scheduled_jobs.sql",
    "0011_agent2_scheduler_claiming.sql",
    "0012_schema_hardening.sql",
)

SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW())
);
"""


def migrations_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "supabase" / "migrations"


def migration_path(filename: str) -> Path:
    path = migrations_dir() / filename
    if not path.is_file():
        raise FileNotFoundError(f"Missing migration file: {path}")
    return path


def list_migrations() -> list[Path]:
    """Files the Python runner applies (0001–0012). Later SQL is applied in the dashboard."""
    return [migration_path(name) for name in MIGRATION_FILES]


def list_on_disk_migrations() -> list[str]:
    """Every numbered SQL file in supabase/migrations, including 0013–0024."""
    names = sorted(path.name for path in migrations_dir().glob("*.sql"))
    return names


def split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(buffer).strip().rstrip(";"))
            buffer = []
    if buffer:
        statements.append("\n".join(buffer).strip().rstrip(";"))
    return [item for item in statements if item]


def fetch_applied_migrations(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'schema_migrations'
            )
            """
        )
        if not cur.fetchone()[0]:
            return set()
        cur.execute("SELECT filename FROM public.schema_migrations ORDER BY filename")
        return {row[0] for row in cur.fetchall()}


def migration_status(conn) -> dict:
    applied = fetch_applied_migrations(conn)
    pending = [name for name in MIGRATION_FILES if name not in applied]
    return {
        "applied": [name for name in MIGRATION_FILES if name in applied],
        "pending": pending,
        "total": len(MIGRATION_FILES),
        "complete": not pending,
    }


def apply_migrations(conn, *, only_pending: bool = True) -> list[str]:
    """Apply migrations in order. Returns filenames applied in this run."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA_MIGRATIONS_DDL)
    conn.commit()

    applied_before = fetch_applied_migrations(conn)
    newly_applied: list[str] = []

    for filename in MIGRATION_FILES:
        if only_pending and filename in applied_before:
            continue
        sql = migration_path(filename).read_text(encoding="utf-8")
        with conn.cursor() as cur:
            for statement in split_sql_statements(sql):
                cur.execute(statement)
            cur.execute(
                """
                INSERT INTO public.schema_migrations (filename)
                VALUES (%s)
                ON CONFLICT (filename) DO NOTHING
                """,
                (filename,),
            )
        conn.commit()
        newly_applied.append(filename)

    return newly_applied
