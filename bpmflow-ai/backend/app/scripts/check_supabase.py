"""Live Supabase connectivity checks (REST + optional Postgres).

Run from bpmflow-ai/backend:
  python -m app.scripts.check_supabase

Exits 0 when Supabase REST is reachable. Postgres pooler failures are
reported but do not fail the check when REST works (many networks block
6543 while HTTPS/443 remains open).
"""

from __future__ import annotations

import sys
from urllib.parse import unquote, urlparse


def main() -> int:
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.core.config import settings
    from app.core.supabase_rest import ping_rest, rest_select, supabase_rest_configured

    print("SUPABASE_URL:", settings.SUPABASE_URL or "(missing)")
    print("REST configured:", supabase_rest_configured())

    if not supabase_rest_configured():
        print("FAIL: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
        return 1

    ok = ping_rest()
    print("REST ping /rest/v1/processes:", "OK" if ok else "FAIL")
    if not ok:
        return 1

    rows = rest_select("processes", {"select": "id", "limit": "1"})
    print(f"REST processes readable: OK ({len(rows)} row(s) sampled)")

    # Optional schema probe for Agent 2 migration 0005
    from app.core.supabase_rest import _client

    with _client() as client:
        col = client.get(
            "/rest/v1/processes",
            params={"select": "execution_status", "limit": "1"},
        )
        if col.status_code == 200:
            print("Migration 0005 columns: present")
        else:
            print(
                "Migration 0005 columns: MISSING — apply "
                "supabase/migrations/0005_agent2_execution.sql in the "
                "Supabase SQL Editor"
            )

    # Optional Postgres pooler probe (non-fatal)
    url = settings.DATABASE_URL or ""
    if url.startswith("postgresql"):
        try:
            import psycopg2
            from sqlalchemy.engine import make_url

            u = make_url(url)
            password = unquote(u.password or "")
            conn = psycopg2.connect(
                host=u.host,
                port=u.port or 6543,
                dbname=u.database or "postgres",
                user=u.username,
                password=password,
                sslmode="require",
                connect_timeout=5,
            )
            conn.close()
            print("Postgres pooler: OK")
        except Exception as exc:
            print(f"Postgres pooler: UNAVAILABLE ({type(exc).__name__}: {str(exc).splitlines()[0][:120]})")
            print(
                "  Hint: copy the exact connection string from Supabase "
                "Dashboard → Project Settings → Database (URI). Region must "
                "match; enable the IPv4 add-on if db.<ref>.supabase.co is "
                "IPv6-only on your network."
            )
    else:
        print("Postgres: DATABASE_URL not set")

    print("RESULT: Supabase REST reachable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
