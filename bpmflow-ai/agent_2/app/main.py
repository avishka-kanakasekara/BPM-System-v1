"""
Agent 2 — FastAPI Main Application Entry Point

Intelligent Workflow Execution, RPA & Process Optimization Agent (Agent 2)
Platform: BPMFlow AI

Features:
- Structured JSON logging (agent, model, action, reason, confidence)
- Inbound inter-agent endpoint (Agent 4 JWT authenticated message handling)
- Dashboard read endpoints (receipts, KPIs, recommendations, audit logs)
- Human Governance Gate (Rule #5 human approval/rejection endpoints)
- Health & readiness endpoints
- CORS middleware configuration
"""

import json
import logging
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database.session import ensure_database_schema
from app.routers import governance, messages, read


# ---------------------------------------------------------------------------
# Structured JSON Logging Configuration (Transparency & Explainability)
# ---------------------------------------------------------------------------

class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": self.formatTime(record),
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "agent"):
            log_obj["agent"] = record.agent
        if hasattr(record, "model"):
            log_obj["model"] = record.model
        if hasattr(record, "action"):
            log_obj["action"] = record.action
        if hasattr(record, "reason"):
            log_obj["reason"] = record.reason
        if hasattr(record, "confidence"):
            log_obj["confidence"] = record.confidence
        return json.dumps(log_obj)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(StructuredJsonFormatter())

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Replace existing handlers to prevent duplicate output
for h in root_logger.handlers[:]:
    root_logger.removeHandler(h)
root_logger.addHandler(handler)

logger = logging.getLogger("agent_2.main")

# ---------------------------------------------------------------------------
# FastAPI Application Initialization
# ---------------------------------------------------------------------------

app = FastAPI(
    title="BPMFlow AI — Agent 2 (Workflow Execution & Optimization)",
    description=(
        "Bounded-autonomy LLM agent responsible for intelligent workflow execution, "
        "RPA integration, and business process optimization."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(messages.router)
app.include_router(read.router)
app.include_router(governance.router)


@app.on_event("startup")
async def startup_event():
    logger.info("Agent 2 (Workflow Execution & Optimization Agent) started successfully.")
    try:
        backend = await ensure_database_schema()
        logger.info(f"Agent 2 database schema ensured ({backend}).")
    except Exception as exc:
        logger.warning(f"Could not ensure Agent 2 database schema: {exc}")


@app.get("/", summary="Root Endpoint")
async def root():
    return {
        "agent": "Agent 2 — Intelligent Workflow Execution, RPA & Process Optimization Agent",
        "version": "1.0.0",
        "status": "running",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health", summary="Health Check")
async def health():
    return {
        "status": "healthy",
        "service": "BPMFlow AI — Agent 2",
        "database": "configured" if settings.DATABASE_URL else "sqlite_fallback",
        "gemini": "configured" if settings.GEMINI_API_KEY and not settings.GEMINI_OFFLINE else "offline_stub_mode",
        "email_dry_run": settings.EMAIL_DRY_RUN,
    }


@app.get("/readiness", summary="Readiness Probe")
async def readiness():
    return {
        "status": "ready",
        "migrations": "current",
        "agent_id": "agent_2",
    }
