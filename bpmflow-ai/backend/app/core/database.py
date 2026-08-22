"""Shared database access for Agent 1 (sync) and Agents 3/4 (async).

Sync path (Agent 1 discovery):
    get_sync_engine, get_sync_session_factory, get_sync_db
    Falls back to None when Postgres is unreachable so REST persistence can run.

Async path (Agent 3, Agent 4, security deps — developer-branch names):
    get_engine, get_session_factory, get_db, get_session, init_db, close_db
    Lazy asyncpg engine; no connection at import time.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Optional

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_MIGRATION_FILE = (
    Path(__file__).resolve().parents[3] / "supabase" / "migrations" / "0002_agent1_discovery.sql"
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

# Global engine and session factory (initialized lazily)
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


class Base(DeclarativeBase):
    """ORM metadata base used by Agent 1 models."""

    pass


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _to_asyncpg_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


# ---------------------------------------------------------------------------
# Agent 1 — sync SQLAlchemy
# ---------------------------------------------------------------------------


def _create_sync_engine(url: str) -> Engine:
    connect_args: dict = {}
    kwargs: dict = {"pool_pre_ping": True}
    if _is_sqlite(url):
        connect_args["check_same_thread"] = False
    else:
        connect_args["connect_timeout"] = 8
        if "sslmode=" not in url:
            connect_args["sslmode"] = "require"
        if ":6543" in url:
            kwargs["poolclass"] = NullPool
    return create_engine(url, connect_args=connect_args, **kwargs)


def _ping(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def _split_sql_statements(sql: str) -> list[str]:
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


def apply_agent1_schema(engine: Engine) -> None:
    """Create/alter Agent 1 tables. Postgres uses the SQL migration; SQLite uses ORM metadata."""
    if _is_sqlite(str(engine.url)):
        import app.models  # noqa: F401

        Base.metadata.create_all(bind=engine)
        return

    if not _MIGRATION_FILE.is_file():
        raise FileNotFoundError(f"Missing migration file: {_MIGRATION_FILE}")

    sql = _MIGRATION_FILE.read_text(encoding="utf-8")
    with engine.begin() as connection:
        for statement in _split_sql_statements(sql):
            try:
                connection.execute(text(statement))
            except Exception as exc:
                logger.warning(
                    "schema_statement_skipped",
                    extra={"error": str(exc), "statement": statement[:80]},
                )
    logger.info("agent1_schema_applied", extra={"migration": str(_MIGRATION_FILE.name)})


@lru_cache
def get_sync_engine() -> Engine | None:
    url = settings.DATABASE_URL
    try:
        engine = _create_sync_engine(url)
        _ping(engine)
        apply_agent1_schema(engine)
        import app.models  # noqa: F401

        if _is_sqlite(url):
            Base.metadata.create_all(bind=engine)
        logger.info("postgres_connected")
        return engine
    except Exception as exc:
        logger.warning(
            "postgres_unavailable_using_supabase_rest",
            extra={"error": str(exc)},
        )
        return None


@lru_cache
def get_sync_session_factory() -> sessionmaker[Session] | None:
    engine = get_sync_engine()
    if engine is None:
        return None
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_sync_db() -> Generator[Session | None, None, None]:
    """Yield a sync session when Postgres is up; otherwise None (Supabase REST)."""
    factory = get_sync_session_factory()
    if factory is None:
        yield None
        return
    db = factory()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Agents 3/4 — async SQLAlchemy (developer-branch public names)
# ---------------------------------------------------------------------------


def get_database_url() -> str:
    """Return DATABASE_URL in postgresql+asyncpg:// form.

    Reads os.environ first so Agent 3 tests can swap the URL without clearing
    the Settings lru_cache. Falls back to settings.DATABASE_URL.
    """
    database_url = os.getenv("DATABASE_URL") or settings.DATABASE_URL
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not configured")
    return _to_asyncpg_url(database_url)


def get_engine() -> AsyncEngine:
    """Lazy shared async engine (Agent 3/4). Raises if DATABASE_URL is missing."""
    global _engine, _session_factory

    if _engine is None:
        database_url = get_database_url()
        connect_args: dict = {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        }
        _engine = create_async_engine(
            database_url,
            echo=False,
            poolclass=NullPool,
            connect_args=connect_args,
        )
        _session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Lazy shared async session factory (Agent 3/4)."""
    global _session_factory

    if _session_factory is None:
        get_engine()

    assert _session_factory is not None
    return _session_factory


async def dispose_engine() -> None:
    """Dispose the shared engine and session factory.

    This should be called during application shutdown to properly
    close all database connections.
    """
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


@asynccontextmanager
async def get_session():
    """Context manager for getting a database session with proper cleanup.

    This context manager:
    - Creates a session from the shared session factory
    - Yields the session for use
    - Closes the session in the finally block
    - Rolls back on error if the session is still active

    Yields:
        AsyncSession: The database session
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


# ============================================================================
# FastAPI Dependency
# ============================================================================


async def get_db():
    """FastAPI dependency to get a database session.

    This dependency provides a database session with proper lifecycle
    management. The session is automatically closed after the request.

    Yields:
        AsyncSession: The database session
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI async session dependency used by Agent 3/4 and security."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    try:
        get_engine()
    except ValueError:
        return


async def close_db() -> None:
    """Close the database engine (called during application shutdown).

    This function should be called during FastAPI lifespan shutdown
    to properly dispose of the engine and close all connections.
    """
    await dispose_engine()
