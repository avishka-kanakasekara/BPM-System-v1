"""Report applied vs pending SQL migrations.

Run from bpmflow-ai/backend:
  python -m app.scripts.migration_status
"""

from __future__ import annotations

import sys
from urllib.parse import unquote

from app.core.migrations import MIGRATION_FILES, migration_status


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
    print(f"Expected migrations ({len(MIGRATION_FILES)}):")
    for name in MIGRATION_FILES:
        print(f"  - {name}")

    try:
        conn = _connect()
    except Exception as exc:
        print()
        print(f"Postgres: UNAVAILABLE ({type(exc).__name__})")
        print("Cannot read schema_migrations without Postgres connectivity.")
        return 1

    try:
        status = migration_status(conn)
        print()
        print(f"Applied ({len(status['applied'])}):")
        for name in status["applied"]:
            print(f"  ✓ {name}")
        print()
        print(f"Pending ({len(status['pending'])}):")
        for name in status["pending"]:
            print(f"  · {name}")
        print()
        print("Complete:", status["complete"])
        return 0 if status["complete"] else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
