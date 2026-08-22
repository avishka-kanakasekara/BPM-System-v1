from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup and shutdown events:
    - Startup: Initialize database engine (lazy, no connection yet)
    - Shutdown: Dispose database engine and close connections, close Agent 3 LLM client
    """
    await init_db()
    yield
    await close_db()
    from app.agents.agent3_resources.runtime_config import close_agent3_llm_runtime

    await close_agent3_llm_runtime()


app = FastAPI(
    title="BPMFlow AI",
    description="Four-agent, human-supervised agentic AI platform for Business Process Management",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://localhost:3000"],  # Vite default ports
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
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "configured" if settings.DATABASE_URL else "not configured",
        "supabase": "configured" if settings.SUPABASE_URL else "not configured",
    }


# Agent 4 + Agent 3 routes under /api/v1
app.include_router(api_router, prefix="/api/v1")
