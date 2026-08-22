"""Shared API v1 router for all agents.

Aggregates Agent 1 discovery, Agent 3 allocation, and Agent 4
process/approval/exception/audit/auth routes. Each agent router keeps its own prefix.
Mounted from main.py with prefix=/api/v1.
"""

from fastapi import APIRouter

from app.api.v1.routes_agent1 import router as agent1_router
from app.api.v1.routes_agent3 import router as agent3_router
from app.api.v1.routes_approvals import router as approvals_router
from app.api.v1.routes_audit import router as audit_router
from app.api.v1.routes_auth import router as auth_router
from app.api.v1.routes_exceptions import router as exceptions_router
from app.api.v1.routes_process import router as process_router

api_router = APIRouter()

# Agent 1 — /api/v1/agent1/discover, /processes
api_router.include_router(agent1_router, prefix="/agent1", tags=["agent1"])

# Agent 4
api_router.include_router(process_router)
api_router.include_router(approvals_router)
api_router.include_router(exceptions_router)
api_router.include_router(audit_router)
api_router.include_router(auth_router)

# Agent 3 — paths like /api/v1/agent3/allocations
api_router.include_router(agent3_router)
