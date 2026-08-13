"""Agent 3-local async session factory helpers (no global engine)."""

from __future__ import annotations

from typing import Callable, Tuple

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from .postgres_resource_repository import PostgresResourceRepository, SessionFactory


def normalize_async_database_url(database_url: str) -> str:
    """Convert a standard PostgreSQL URL to the asyncpg SQLAlchemy dialect."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    raise ValueError("Database URL must use postgresql:// or postgresql+asyncpg://")


def create_async_session_factory(
    database_url: str,
    *,
    echo: bool = False,
) -> Tuple[AsyncEngine, SessionFactory]:
    """Create a dedicated async engine and session factory for Agent 3 repositories."""
    engine = create_async_engine(
        normalize_async_database_url(database_url),
        echo=echo,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, factory


def create_postgres_resource_repository(
    session_factory: SessionFactory,
) -> PostgresResourceRepository:
    """Build a PostgresResourceRepository from an injected session factory."""
    return PostgresResourceRepository(session_factory=session_factory)
