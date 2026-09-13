"""Apply pending Supabase SQL migrations when Postgres is reachable.

Run from bpmflow-ai/backend:
  python -m app.scripts.apply_pending_migrations

Uses DATABASE_URL from backend/.env. When the pooler is unavailable, prints
the combined pending SQL so you can paste it into Supabase Dashboard → SQL Editor.

Migration status:
  python -m app.scripts.migration_status
"""

from __future__ import annotations

import sys
from urllib.parse import unquote

from app.core.migrations import apply_migrations, list_migrations, migration_status


def _connect():
    import psycopg2
    from sqlalchemy.engine import make_url

    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.core.config import settings

    url = settings.DATABASE_URL or ""
    if not url.startswith("postgresql"):
        raise RuntimeError("DATABASE_URL is not configured for Postgres")

    u = make_url(url.replace("postgresql+asyncpg://", "postgresql://"))
    password = unquote(u.password or "")
    return psycopg2.connect(
        host=u.host,
        port=u.port or 5432,
        dbname=u.database or "postgres",
        user=u.username,
        password=password,
        sslmode="require",
        connect_timeout=12,
    )


def main() -> int:
    all_names = [p.name for p in list_migrations()]
    print("Migration order:", ", ".join(all_names))

    try:
        conn = _connect()
    except Exception as exc:
        print(f"Postgres: UNAVAILABLE ({type(exc).__name__}: {str(exc).splitlines()[0][:160]})")
        print()
        print("Apply manually in Supabase Dashboard → SQL Editor (pending files only).")
        print("Check status with: python -m app.scripts.migration_status")
        return 1

    try:
        before = migration_status(conn)
        print(f"Applied: {len(before['applied'])}/{before['total']}")
        if before["pending"]:
            print("Pending:", ", ".join(before["pending"]))
        applied_now = apply_migrations(conn, only_pending=True)
        after = migration_status(conn)
        print("Postgres: OK")
        if applied_now:
            print("Newly applied:", ", ".join(applied_now))
        else:
            print("No pending migrations.")
        print(f"Complete: {after['complete']}")
        return 0 if after["complete"] else 1
    except Exception as exc:
        conn.rollback()
        print(f"Migration failed: {type(exc).__name__}: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
