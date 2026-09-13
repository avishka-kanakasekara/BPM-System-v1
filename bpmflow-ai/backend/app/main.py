from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.v1.router import api_router
from app.core import shutdown as shutdown_state
from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.health import live_payload, ready_payload, run_dependency_probes
from app.core.logging import configure_logging, get_logger
from app.core.middleware import CorrelationMiddleware, RateLimitMiddleware, RequestGuardMiddleware

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: validate prod config, init DB, scheduler. Shutdown: drain, release leases."""
    try:
        settings.assert_production_config()
    except RuntimeError:
        logger.exception("production_config_invalid")
        raise
    try:
        await init_db()
    except Exception:
        logger.warning("async_db_init_skipped", exc_info=True)
    try:
        from app.agents.agent2_execution.scheduler import start_scheduler

        start_scheduler()
    except Exception:
        logger.warning("agent2_scheduler_start_skipped", exc_info=True)
    yield
    shutdown_state.begin_shutdown()
    drained = await shutdown_state.wait_for_drain(settings.SHUTDOWN_DRAIN_SECONDS)
    logger.info(
        "shutdown_drain_complete",
        extra={"drained": drained, "in_flight": shutdown_state.in_flight_count()},
    )
    try:
        from app.agents.agent2_execution.scheduler import stop_scheduler

        await stop_scheduler(release_leases=True)
    except Exception:
        logger.warning("agent2_scheduler_stop_skipped", exc_info=True)
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

# Outermost first: correlation → rate limit → request guard → CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=(
        r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
        if settings.is_development
        else None
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID", "X-Request-ID"],
)
app.add_middleware(RequestGuardMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CorrelationMiddleware)


@app.get("/")
async def root():
    return {
        "message": "BPMFlow AI API",
        "version": "0.1.0",
        "status": "running",
        "env": settings.ENV,
    }


@app.get("/health/live")
async def health_live():
    """Process is up — no dependency checks."""
    return live_payload()


@app.get("/health/ready")
async def health_ready(response: Response):
    """Ready only when a persistence backend and auth config are usable."""
    payload = await ready_payload()
    if payload["status"] != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload


@app.get("/health")
@app.get("/health/deps")
async def health_deps(response: Response):
    """Full dependency probe report (truthful when a dependency is broken)."""
    report = await run_dependency_probes()
    overall = "healthy" if report["ready"] else "degraded"
    if not report["ready"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": overall, "env": settings.ENV, **report}


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
