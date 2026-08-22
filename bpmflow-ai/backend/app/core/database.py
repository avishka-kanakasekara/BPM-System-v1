from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_MIGRATION_FILE = (
    Path(__file__).resolve().parents[3] / "supabase" / "migrations" / "0002_agent1_discovery.sql"
)


class Base(DeclarativeBase):
    pass


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _create_engine(url: str) -> Engine:
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
def get_engine() -> Engine | None:
    url = settings.DATABASE_URL
    try:
        engine = _create_engine(url)
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
def get_session_factory() -> sessionmaker[Session] | None:
    engine = get_engine()
    if engine is None:
        return None
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session | None, None, None]:
    """Yield a SQLAlchemy session when Postgres is up; otherwise None (Supabase REST)."""
    factory = get_session_factory()
    if factory is None:
        yield None
        return
    db = factory()
    try:
        yield db
    finally:
        db.close()
