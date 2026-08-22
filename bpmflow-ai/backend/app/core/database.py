"""Shared database engine and session factory for Agent 3, Agent 4, and other agents.

This module provides lazy database initialization to ensure:
- No connection at import time
- Single shared engine across all agents
- Proper session lifecycle management
- Engine disposal on application shutdown
- Application imports work without DATABASE_URL (engine created on first use)

The engine is created lazily on first access to avoid immediate database
connections during import, which is important for testing and startup.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

# Global engine and session factory (initialized lazily)
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

# Base class for models (legacy; ORM models use app.models.base.Base)
Base = declarative_base()


def get_database_url() -> str:
    """Get the database URL from environment.

    Returns:
        The database URL in asyncpg format

    Raises:
        ValueError: If DATABASE_URL is not configured
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not configured")

    # Convert to async format for asyncpg
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")

    return database_url


def get_engine() -> AsyncEngine:
    """Get or create the shared async engine (lazy initialization).

    This function creates the engine on first call and reuses it for
    subsequent calls. This ensures no database connection is made at
    import time.

    Returns:
        The shared async engine

    Raises:
        ValueError: If DATABASE_URL is not configured
    """
    global _engine, _session_factory

    if _engine is None:
        database_url = get_database_url()
        _engine = create_async_engine(
            database_url,
            echo=False,  # Set to False in production
            poolclass=NullPool,  # Use NullPool for serverless environments like Supabase
            connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
        )

        # Create session factory with the engine
        _session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the shared session factory (lazy initialization).

    Returns:
        The shared async session factory

    Raises:
        ValueError: If DATABASE_URL is not configured
    """
    global _session_factory

    if _session_factory is None:
        # Ensure engine is created first
        get_engine()

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


# ============================================================================
# Application Lifespan Support
# ============================================================================


async def init_db() -> None:
    """Initialize the database engine (called during application startup).

    This function can be called during FastAPI lifespan startup to
    pre-initialize the engine, ensuring it's ready for the first request.

    When DATABASE_URL is unset (unit tests / local import), skip eagerly
    creating the engine so the application can still start.
    """
    try:
        get_engine()
    except ValueError:
        # DATABASE_URL not configured — keep lazy init for first real use
        return


async def close_db() -> None:
    """Close the database engine (called during application shutdown).

    This function should be called during FastAPI lifespan shutdown
    to properly dispose of the engine and close all connections.
    """
    await dispose_engine()
