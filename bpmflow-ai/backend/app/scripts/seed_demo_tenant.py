"""Idempotent demo-tenant seeder for Agent 3 allocation scenarios.

Run from bpmflow-ai/backend:
  python -m app.scripts.seed_demo_tenant

Requires migrations 0004 (resource persistence), 0005 (synthetic seed), and
0006 (write path) to be applied first. Applies the base synthetic seed from
0005_agent3_synthetic_seed.sql when missing, then upserts the demo expansion
(>=4 roles, >=8 human profiles, budgets, evidence, SoD conflict).
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import unquote

from app.agents.agent3_resources.repositories.seed_constants import (
    AGENT3_DEMO_TENANT_ID,
    MIGRATION_0003_FILENAME,
)
from app.agents.agent3_resources.repositories.table_mapping import MIGRATION_0002_FILENAME
from app.agents.agent3_resources.repositories.write_table_mapping import MIGRATION_0004_FILENAME
from app.core.migrations import apply_migrations, migration_status

BPMFLOW_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = BPMFLOW_ROOT / "supabase" / "migrations"

DEMO_TENANT_SUPPLEMENT_SQL = """
-- Demo tenant expansion: roles, humans, budgets, evidence (idempotent)

INSERT INTO public.roles (id, tenant_id, code, name)
VALUES
    ('00000000-0000-0000-0000-000000000103', '00000000-0000-0000-0000-000000000001', 'buyer', 'Synthetic Buyer Role'),
    ('00000000-0000-0000-0000-000000000104', '00000000-0000-0000-0000-000000000001', 'manager', 'Synthetic Manager Role')
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.resources (
    id, tenant_id, name, type, is_active, employee_identifier,
    capacity, availability_percentage, cost_per_hour, department, skills
) VALUES
    (
        '00000000-0000-0000-0000-000000000017',
        '00000000-0000-0000-0000-000000000001',
        'Synthetic Employee Buyer',
        'HUMAN', TRUE, 'SYN-EMP-017',
        1, 100, 0.00, 'SYN-DEP-PROC', ARRAY['python']
    ),
    (
        '00000000-0000-0000-0000-000000000018',
        '00000000-0000-0000-0000-000000000001',
        'Synthetic Employee Manager',
        'HUMAN', TRUE, 'SYN-EMP-018',
        1, 100, 0.00, 'SYN-DEP-OPS', ARRAY['python', 'fastapi']
    ),
    (
        '00000000-0000-0000-0000-000000000022',
        '00000000-0000-0000-0000-000000000001',
        'Synthetic Budget IT',
        'BUDGET', TRUE,
        NULL, 100, 0.00, 'SYN-DEP-IT', ARRAY[]::TEXT[]
    )
ON CONFLICT (id) DO UPDATE SET
    tenant_id = EXCLUDED.tenant_id,
    name = EXCLUDED.name,
    type = EXCLUDED.type,
    is_active = EXCLUDED.is_active;

INSERT INTO public.resource_roles (tenant_id, resource_id, role_id, is_primary)
VALUES
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000017', '00000000-0000-0000-0000-000000000101', TRUE),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000017', '00000000-0000-0000-0000-000000000103', FALSE),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000018', '00000000-0000-0000-0000-000000000101', TRUE),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000018', '00000000-0000-0000-0000-000000000104', FALSE)
ON CONFLICT (tenant_id, resource_id, role_id) DO NOTHING;

INSERT INTO public.resource_skills (tenant_id, resource_id, skill_id, proficiency, certified_at)
VALUES
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000017', '00000000-0000-0000-0000-000000000201', 85.00, TIMESTAMPTZ '2025-06-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000018', '00000000-0000-0000-0000-000000000201', 82.00, TIMESTAMPTZ '2025-06-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000018', '00000000-0000-0000-0000-000000000202', 78.00, TIMESTAMPTZ '2025-06-01 12:00:00+00')
ON CONFLICT (tenant_id, resource_id, skill_id) DO NOTHING;

INSERT INTO public.resource_authorities (tenant_id, resource_id, authority_id, granted_at, valid_until)
VALUES
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000017', '00000000-0000-0000-0000-000000000301', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000018', '00000000-0000-0000-0000-000000000302', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL)
ON CONFLICT (tenant_id, resource_id, authority_id) DO NOTHING;

INSERT INTO public.human_resource_profiles (
    tenant_id, resource_id, max_workload_pct, evidence_checked_at, evidence_valid_until
) VALUES
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000017', 80.00, TIMESTAMPTZ '2025-12-01 12:00:00+00', TIMESTAMPTZ '2026-12-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000018', 80.00, TIMESTAMPTZ '2025-12-01 12:00:00+00', TIMESTAMPTZ '2026-12-01 12:00:00+00')
ON CONFLICT (tenant_id, resource_id) DO UPDATE SET
    max_workload_pct = EXCLUDED.max_workload_pct,
    evidence_checked_at = EXCLUDED.evidence_checked_at,
    evidence_valid_until = EXCLUDED.evidence_valid_until;

INSERT INTO public.resource_availability (
    id, tenant_id, resource_id, available_from, available_until, reason
) VALUES
    ('00000000-0000-0000-0000-000000000507', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000017', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL, 'Synthetic open availability'),
    ('00000000-0000-0000-0000-000000000508', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000018', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL, 'Synthetic open availability')
ON CONFLICT (id) DO UPDATE SET
    available_from = EXCLUDED.available_from,
    available_until = EXCLUDED.available_until,
    reason = EXCLUDED.reason;

INSERT INTO public.workload_snapshots (
    id, tenant_id, resource_id, snapshot_at, current_workload_pct, max_workload_pct
) VALUES
    ('00000000-0000-0000-0000-000000000608', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000017', TIMESTAMPTZ '2025-12-01 12:00:00+00', 25.00, 80.00),
    ('00000000-0000-0000-0000-000000000609', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000018', TIMESTAMPTZ '2025-12-01 12:00:00+00', 30.00, 80.00)
ON CONFLICT (id) DO UPDATE SET
    snapshot_at = EXCLUDED.snapshot_at,
    current_workload_pct = EXCLUDED.current_workload_pct,
    max_workload_pct = EXCLUDED.max_workload_pct;

INSERT INTO public.budget_resource_profiles (
    tenant_id, resource_id, cost_centre, currency, available_balance,
    authorization_limit, valid_from, valid_until, evidence_checked_at, evidence_valid_until
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000022',
    'CC-IT-100', 'USD', 120000.00, 60000.00,
    TIMESTAMPTZ '2025-01-01 00:00:00+00', TIMESTAMPTZ '2026-12-31 23:59:59+00',
    TIMESTAMPTZ '2025-12-01 12:00:00+00', TIMESTAMPTZ '2026-12-01 12:00:00+00'
)
ON CONFLICT (tenant_id, resource_id) DO UPDATE SET
    cost_centre = EXCLUDED.cost_centre,
    available_balance = EXCLUDED.available_balance,
    authorization_limit = EXCLUDED.authorization_limit;

INSERT INTO public.evidence_references (
    id, tenant_id, resource_id, evidence_key, payload, checked_at, valid_until
)
SELECT * FROM (VALUES
    (
        '00000000-0000-0000-0000-000000000711'::uuid,
        '00000000-0000-0000-0000-000000000001'::uuid,
        '00000000-0000-0000-0000-000000000010'::uuid,
        'availability',
        '{"source":"seed_demo_tenant","scenario":"eligible"}'::jsonb,
        TIMESTAMPTZ '2025-12-01 12:00:00+00',
        TIMESTAMPTZ '2026-12-01 12:00:00+00'
    ),
    (
        '00000000-0000-0000-0000-000000000712'::uuid,
        '00000000-0000-0000-0000-000000000001'::uuid,
        '00000000-0000-0000-0000-000000000010'::uuid,
        'workload',
        '{"source":"seed_demo_tenant","scenario":"eligible"}'::jsonb,
        TIMESTAMPTZ '2025-12-01 12:00:00+00',
        TIMESTAMPTZ '2026-12-01 12:00:00+00'
    ),
    (
        '00000000-0000-0000-0000-000000000713'::uuid,
        '00000000-0000-0000-0000-000000000001'::uuid,
        '00000000-0000-0000-0000-000000000014'::uuid,
        'availability',
        '{"source":"seed_demo_tenant","scenario":"sod_conflict"}'::jsonb,
        TIMESTAMPTZ '2025-12-01 12:00:00+00',
        TIMESTAMPTZ '2026-12-01 12:00:00+00'
    ),
    (
        '00000000-0000-0000-0000-000000000714'::uuid,
        '00000000-0000-0000-0000-000000000001'::uuid,
        '00000000-0000-0000-0000-000000000014'::uuid,
        'workload',
        '{"source":"seed_demo_tenant","scenario":"sod_conflict"}'::jsonb,
        TIMESTAMPTZ '2025-12-01 12:00:00+00',
        TIMESTAMPTZ '2026-12-01 12:00:00+00'
    ),
    (
        '00000000-0000-0000-0000-000000000715'::uuid,
        '00000000-0000-0000-0000-000000000001'::uuid,
        '00000000-0000-0000-0000-000000000017'::uuid,
        'availability',
        '{"source":"seed_demo_tenant","scenario":"buyer"}'::jsonb,
        TIMESTAMPTZ '2025-12-01 12:00:00+00',
        TIMESTAMPTZ '2026-12-01 12:00:00+00'
    ),
    (
        '00000000-0000-0000-0000-000000000716'::uuid,
        '00000000-0000-0000-0000-000000000001'::uuid,
        '00000000-0000-0000-0000-000000000017'::uuid,
        'workload',
        '{"source":"seed_demo_tenant","scenario":"buyer"}'::jsonb,
        TIMESTAMPTZ '2025-12-01 12:00:00+00',
        TIMESTAMPTZ '2026-12-01 12:00:00+00'
    ),
    (
        '00000000-0000-0000-0000-000000000717'::uuid,
        '00000000-0000-0000-0000-000000000001'::uuid,
        '00000000-0000-0000-0000-000000000018'::uuid,
        'availability',
        '{"source":"seed_demo_tenant","scenario":"manager"}'::jsonb,
        TIMESTAMPTZ '2025-12-01 12:00:00+00',
        TIMESTAMPTZ '2026-12-01 12:00:00+00'
    ),
    (
        '00000000-0000-0000-0000-000000000718'::uuid,
        '00000000-0000-0000-0000-000000000001'::uuid,
        '00000000-0000-0000-0000-000000000018'::uuid,
        'workload',
        '{"source":"seed_demo_tenant","scenario":"manager"}'::jsonb,
        TIMESTAMPTZ '2025-12-01 12:00:00+00',
        TIMESTAMPTZ '2026-12-01 12:00:00+00'
    ),
    (
        '00000000-0000-0000-0000-000000000719'::uuid,
        '00000000-0000-0000-0000-000000000001'::uuid,
        '00000000-0000-0000-0000-000000000022'::uuid,
        'budget_profile',
        '{"source":"seed_demo_tenant","scenario":"it_budget"}'::jsonb,
        TIMESTAMPTZ '2025-12-01 12:00:00+00',
        TIMESTAMPTZ '2026-12-01 12:00:00+00'
    )
) AS seed(id, tenant_id, resource_id, evidence_key, payload, checked_at, valid_until)
ON CONFLICT (tenant_id, resource_id, evidence_key) DO UPDATE SET
    payload = EXCLUDED.payload,
    checked_at = EXCLUDED.checked_at,
    valid_until = EXCLUDED.valid_until;
"""


def _connect():
    import psycopg2
    from sqlalchemy.engine import make_url

    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.core.config import settings

    url = settings.DATABASE_URL or ""
    if not url.startswith("postgresql"):
        raise RuntimeError("DATABASE_URL is not configured for Postgres")

    parsed = make_url(url.replace("postgresql+asyncpg://", "postgresql://"))
    password = unquote(parsed.password or "")
    return psycopg2.connect(
        host=parsed.host,
        port=parsed.port or 5432,
        dbname=parsed.database or "postgres",
        user=parsed.username,
        password=password,
        sslmode="require",
        connect_timeout=12,
    )


def _execute_sql(conn, sql: str) -> None:
    with conn.cursor() as cursor:
        cursor.execute(sql)
    conn.commit()


def _verify_demo_tenant(conn) -> dict[str, int]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM public.roles WHERE tenant_id = %s) AS roles,
                (SELECT COUNT(*) FROM public.resources
                 WHERE tenant_id = %s AND type = 'HUMAN') AS humans,
                (SELECT COUNT(*) FROM public.resources
                 WHERE tenant_id = %s AND type = 'BUDGET') AS budgets,
                (SELECT COUNT(*) FROM public.sod_rules WHERE tenant_id = %s) AS sod_rules,
                (SELECT COUNT(*) FROM public.resource_declared_conflicts
                 WHERE tenant_id = %s) AS sod_conflicts
            """,
            tuple([str(AGENT3_DEMO_TENANT_ID)] * 5),
        )
        roles, humans, budgets, sod_rules, sod_conflicts = cursor.fetchone()
    return {
        "roles": roles,
        "humans": humans,
        "budgets": budgets,
        "sod_rules": sod_rules,
        "sod_conflicts": sod_conflicts,
    }


def seed_demo_tenant(conn) -> dict[str, int]:
    """Apply base seed + demo expansion idempotently."""
    required = {MIGRATION_0002_FILENAME, MIGRATION_0003_FILENAME, MIGRATION_0004_FILENAME}
    status = migration_status(conn)
    missing = required - set(status["applied"])
    if missing:
        raise RuntimeError(
            "Apply Agent 3 migrations first: "
            + ", ".join(sorted(missing))
        )

    base_seed = MIGRATIONS_DIR / MIGRATION_0003_FILENAME
    _execute_sql(conn, base_seed.read_text(encoding="utf-8"))
    _execute_sql(conn, DEMO_TENANT_SUPPLEMENT_SQL)
    return _verify_demo_tenant(conn)


def main() -> int:
    print("Agent 3 demo tenant seeder")
    print("Expected migrations:", MIGRATION_0002_FILENAME, MIGRATION_0003_FILENAME, MIGRATION_0004_FILENAME)

    try:
        conn = _connect()
    except Exception as exc:
        print(f"Postgres: UNAVAILABLE ({type(exc).__name__}: {str(exc).splitlines()[0][:160]})")
        print("Configure DATABASE_URL in backend/.env, apply migrations, then re-run.")
        return 1

    try:
        pending = migration_status(conn)["pending"]
        if pending:
            print("Applying pending migrations:", ", ".join(pending))
            apply_migrations(conn, only_pending=True)

        counts = seed_demo_tenant(conn)
        print("Postgres: OK")
        print(
            "Demo tenant counts — "
            f"roles={counts['roles']} humans={counts['humans']} budgets={counts['budgets']} "
            f"sod_rules={counts['sod_rules']} sod_conflicts={counts['sod_conflicts']}"
        )
        ok = counts["roles"] >= 4 and counts["humans"] >= 8 and counts["budgets"] >= 2
        print("Coherent demo tenant:", "YES" if ok else "NO")
        return 0 if ok else 1
    except Exception as exc:
        conn.rollback()
        print(f"Seed failed: {type(exc).__name__}: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
