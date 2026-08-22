"""
Agent 2 — database sessions on the shared BPMFlow engine.

After integration Agent 2 uses the same async engine and DATABASE_URL as
Agents 3/4 (app.core.database). There is no private SQLite fallback anymore:
all agents persist to one database. If the shared database is unreachable,
get_db_session yields None and Agent 2's persistence helpers degrade
gracefully (they already treat session=None as "no persistence available").
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_engine, get_session_factory

logger = logging.getLogger("agent_2.database.session")


async def ensure_database_schema() -> str:
    """Create missing tables on the shared engine (SQLite/local dev only).

    On Postgres the schema is owned by supabase/migrations; create_all with
    checkfirst still only adds missing tables and never alters existing ones.
    Returns the dialect name of the live backend, or "none".
    """
    # Import inside the function so ORM metadata is fully registered first.
    from app.core.database import Base as CoreBase
    from app.models.base import Base as ModelsBase

    import app.models  # noqa: F401  (register canonical models)
    import app.agents.agent2_execution.database.models  # noqa: F401

    try:
        engine = get_engine()
    except ValueError:
        logger.warning("DATABASE_URL not configured; Agent 2 persistence disabled")
        return "none"

    try:
        async with engine.begin() as conn:
            await conn.run_sync(CoreBase.metadata.create_all)
            await conn.run_sync(ModelsBase.metadata.create_all)
        return engine.dialect.name
    except Exception as exc:
        logger.warning(f"Could not ensure shared schema: {exc}")
        return "none"


async def get_db_session() -> AsyncGenerator[AsyncSession | None, None]:
    """Yield a session on the shared engine, or None when it is unreachable."""
    try:
        factory = get_session_factory()
    except ValueError:
        yield None
        return

    session = factory()
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        await session.close()
        logger.warning(f"Shared database unreachable; Agent 2 runs without persistence: {exc}")
        yield None
        return

    try:
        yield session
    finally:
        await session.close()
