from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: lazy async engine. Shutdown: dispose engine and Agent 3 LLM if present."""
    try:
        await init_db()
    except Exception:
        logger.warning("async_db_init_skipped", exc_info=True)
    yield
    try:
        await close_db()
    except Exception:
        logger.warning("async_db_close_skipped", exc_info=True)
    try:
        from app.agents.agent3_resources.runtime_config import close_agent3_llm_runtime

        await close_agent3_llm_runtime()
    except ImportError:
        pass
    except Exception:
        logger.exception("agent3_llm_shutdown_failed")


app = FastAPI(
    title="BPMFlow AI",
    description="Four-agent, human-supervised agentic AI platform for Business Process Management",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "message": "BPMFlow AI API",
        "version": "0.1.0",
        "status": "running",
        "env": settings.ENV,
    }


@app.get("/health")
async def health_check():
    """Liveness + dependency probe.

    Prefers a fast Supabase REST ping (HTTPS) so environments that block the
    Postgres pooler ports (6543/5432) still report healthy when Supabase is
    reachable. Postgres is probed only when REST is unavailable/unconfigured.
    """
    logger.info("health_check")
    database = "unknown"
    try:
        from app.core.database import get_sync_engine
        from app.core.supabase_rest import ping_rest, supabase_rest_configured
        from sqlalchemy import text

        if supabase_rest_configured() and ping_rest():
            # Do not call get_sync_engine() here — a blocked pooler port can
            # hang for many seconds even though Supabase HTTPS is fine.
            database = "supabase_rest"
        else:
            engine = get_sync_engine()
            if engine is not None:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                database = "postgres"
            else:
                database = "disconnected"
    except Exception as exc:
        logger.exception("health_database_failed")
        database = f"error: {type(exc).__name__}"
    return {
        "status": "healthy" if database in {"postgres", "supabase_rest"} else "degraded",
        "env": settings.ENV,
        "database": database,
        "database_url_configured": bool(settings.DATABASE_URL),
        "supabase": "configured" if settings.SUPABASE_URL else "not configured",
    }


app.include_router(api_router, prefix="/api/v1")


def _file_array_items_as_binary(schema: dict) -> None:
    """Make Swagger UI show file pickers instead of 'Add string item'."""
    for component in (schema.get("components") or {}).get("schemas", {}).values():
        for prop in (component.get("properties") or {}).values():
            items = prop.get("items")
            if not isinstance(items, dict):
                continue
            if items.get("contentMediaType") == "application/octet-stream" or items.get("format") == "binary":
                items["type"] = "string"
                items["format"] = "binary"
                items.pop("contentMediaType", None)


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    _file_array_items_as_binary(schema)
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
