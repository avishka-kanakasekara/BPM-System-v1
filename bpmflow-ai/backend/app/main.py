from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

app = FastAPI(
    title="BPMFlow AI",
    description="Four-agent, human-supervised agentic AI platform for Business Process Management",
    version="0.1.0",
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
    logger.info("health_check")
    database = "unknown"
    try:
        from app.core.database import get_engine
        from app.core.supabase_rest import ping_rest
        from sqlalchemy import text

        engine = get_engine()
        if engine is not None:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            database = "postgres"
        elif ping_rest():
            database = "supabase_rest"
        else:
            database = "disconnected"
    except Exception as exc:
        logger.exception("health_database_failed")
        database = f"error: {type(exc).__name__}"
    return {
        "status": "healthy" if database in {"postgres", "supabase_rest"} else "degraded",
        "env": settings.ENV,
        "agent": "agent1_discovery",
        "database": database,
    }


# Agent 1 discovery. Process, auth, and other-agent routers are not mounted.
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
