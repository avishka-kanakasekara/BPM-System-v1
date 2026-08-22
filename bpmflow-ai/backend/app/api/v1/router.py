<<<<<<< HEAD
"""API v1 router.

Process, approval, exception, audit, and auth demo routes are registered.
Later sections can include:
- task routes
- agent routes
=======
"""Shared API v1 router for all agents.

This module aggregates all agent-specific routers under the /api/v1 prefix.
Each agent's router is included exactly once with its own prefix.
>>>>>>> origin/developer-branch
"""

from fastapi import APIRouter

<<<<<<< HEAD
from app.api.v1.routes_approvals import router as approvals_router
from app.api.v1.routes_audit import router as audit_router
from app.api.v1.routes_auth import router as auth_router
from app.api.v1.routes_exceptions import router as exceptions_router
from app.api.v1.routes_process import router as process_router

api_router = APIRouter()
api_router.include_router(process_router)
api_router.include_router(approvals_router)
api_router.include_router(exceptions_router)
api_router.include_router(audit_router)
api_router.include_router(auth_router)
=======
from app.api.v1.routes_agent3 import router as agent3_router

# Create the shared v1 API router
api_router = APIRouter(prefix="/api/v1")

# Include Agent 3 router with its own prefix
# This will result in paths like /api/v1/agent3/allocations
api_router.include_router(agent3_router)
>>>>>>> origin/developer-branch
