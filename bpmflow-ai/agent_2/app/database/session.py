"""
Agent 2 — Async database session management.

Prefers the configured Supabase/Postgres URL. If that database is unreachable,
falls back to a local SQLite file so the cognitive cycle can still persist
plans, receipts, KPIs, and recommendations.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

logger = logging.getLogger("agent_2.database.session")
_postgres_unreachable = False


def _sqlite_url() -> str:
    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "agent2.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


def _build_engine(url: str):
    connect_args: dict = {}
    if url.startswith("postgresql+asyncpg://"):
        connect_args = {"ssl": "require", "statement_cache_size": 0}
    elif url.startswith("sqlite"):
        connect_args = {"timeout": 30}
    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


postgres_engine = _build_engine(settings.DATABASE_URL) if settings.DATABASE_URL else None
sqlite_engine = _build_engine(_sqlite_url())

PostgresSessionLocal = (
    async_sessionmaker(postgres_engine, expire_on_commit=False, class_=AsyncSession)
    if postgres_engine is not None
    else None
)
SqliteSessionLocal = async_sessionmaker(
    sqlite_engine, expire_on_commit=False, class_=AsyncSession
)

# Preferred engine for startup schema creation; actual requests may fall back.
engine = postgres_engine or sqlite_engine
SessionLocal = PostgresSessionLocal or SqliteSessionLocal


async def _ensure_schema(target_engine) -> None:
    from app.database.models import Base

    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _probe(factory) -> AsyncSession | None:
    session = factory()
    try:
        await session.execute(text("SELECT 1"))
        return session
    except Exception as exc:
        await session.close()
        logger.warning(f"Database probe failed, will try fallback if available: {exc}")
        return None


async def ensure_database_schema() -> str:
    """Create tables on every reachable backend. Returns the preferred live backend name."""
    global _postgres_unreachable
    live = "sqlite"
    if postgres_engine is not None:
        try:
            await _ensure_schema(postgres_engine)
            live = "postgres"
        except Exception as exc:
            _postgres_unreachable = True
            logger.warning(f"Could not ensure Postgres schema: {exc}")
    try:
        await _ensure_schema(sqlite_engine)
    except Exception as exc:
        logger.warning(f"Could not ensure SQLite schema: {exc}")
        if live == "sqlite":
            live = "none"
    return live


async def get_db_session() -> AsyncGenerator[AsyncSession | None, None]:
    global _postgres_unreachable
    session: AsyncSession | None = None
    if PostgresSessionLocal is not None and not _postgres_unreachable:
        session = await _probe(PostgresSessionLocal)
        if session is None:
            _postgres_unreachable = True
    if session is None:
        try:
            await _ensure_schema(sqlite_engine)
        except Exception:
            pass
        session = await _probe(SqliteSessionLocal)
    if session is None:
        yield None
        return
    try:
        yield session
    finally:
        await session.close()
