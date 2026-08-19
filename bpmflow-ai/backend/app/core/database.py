from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
import os
from dotenv import load_dotenv

load_dotenv()

# Convert to asyncpg URL when a Postgres connection string is present.
DATABASE_URL = os.getenv("DATABASE_URL") or ""
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = None
AsyncSessionLocal = None

# Base class for models (legacy; ORM models use app.models.base.Base)
Base = declarative_base()


def _session_factory():
    """Create the async sessionmaker on first use so imports work without DATABASE_URL."""
    global engine, AsyncSessionLocal
    if AsyncSessionLocal is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        engine = create_async_engine(
            DATABASE_URL,
            echo=True,
            poolclass=NullPool,
        )
        AsyncSessionLocal = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return AsyncSessionLocal


async def get_db():
    factory = _session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()
