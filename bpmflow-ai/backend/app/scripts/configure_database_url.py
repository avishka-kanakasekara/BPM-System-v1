"""Validate and optionally update DATABASE_URL for Supabase Postgres.

Run from bpmflow-ai/backend:

  # Test current .env DATABASE_URL
  python -m app.scripts.configure_database_url

  # Test a candidate URI (e.g. pasted from Supabase Dashboard → Connect)
  DATABASE_URL='postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres?sslmode=require' \
    python -m app.scripts.configure_database_url --write

When every probe fails, reset the database password in Supabase Dashboard:
  Project Settings → Database → Reset database password
Then copy the **Session pooler** URI (port 5432) or **Direct connection** URI
and pass it with --write.

Direct host db.<project-ref>.supabase.co requires IPv6 or the Supabase IPv4 add-on.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import unquote

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _probe(url: str) -> tuple[bool, str]:
    import psycopg2
    from sqlalchemy.engine import make_url

    normalized = url.replace("postgresql+asyncpg://", "postgresql://")
    u = make_url(normalized)
    password = unquote(u.password or "")
    try:
        conn = psycopg2.connect(
            host=u.host,
            port=u.port or 5432,
            dbname=u.database or "postgres",
            user=u.username,
            password=password,
            sslmode="require",
            connect_timeout=10,
        )
        cur = conn.cursor()
        cur.execute("select version()")
        version = cur.fetchone()[0]
        conn.close()
        return True, version[:80]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"


def _load_env_url() -> str:
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.core.config import settings

    return settings.DATABASE_URL or ""


def _write_env_url(url: str) -> None:
    if not ENV_PATH.is_file():
        raise SystemExit(f".env not found at {ENV_PATH}")
    lines = ENV_PATH.read_text().splitlines()
    out: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith("DATABASE_URL="):
            out.append(f"DATABASE_URL={url}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"DATABASE_URL={url}")
    ENV_PATH.write_text("\n".join(out) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Supabase DATABASE_URL")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write working DATABASE_URL from env var into backend/.env",
    )
    parser.add_argument(
        "--url",
        default="",
        help="URI to test (default: DATABASE_URL from environment or .env)",
    )
    args = parser.parse_args()

    candidate = (args.url or __import__("os").environ.get("DATABASE_URL") or _load_env_url()).strip()
    if not candidate:
        print("No DATABASE_URL set.")
        print(__doc__)
        return 1

    ok, detail = _probe(candidate)
    if ok:
        print("Postgres connection: OK")
        print("Server:", detail)
        if args.write and args.url:
            _write_env_url(candidate)
            print(f"Wrote DATABASE_URL to {ENV_PATH}")
        return 0

    print("Postgres connection: FAIL")
    print(detail)
    print()
    print("Fix steps:")
    print("  1. Supabase Dashboard → Project Settings → Database")
    print("  2. Reset database password (save the new password)")
    print("  3. Connect → ORMs → copy Session pooler URI (port 5432)")
    print("     User must look like: postgres.<project-ref>")
    print("  4. Run:")
    print('       DATABASE_URL="postgresql://..." python -m app.scripts.configure_database_url --write --url "$DATABASE_URL"')
    print("  5. python -m app.scripts.apply_pending_migrations")
    print()
    print("If direct db.<ref>.supabase.co DNS fails, enable IPv4 add-on or use pooler only.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
