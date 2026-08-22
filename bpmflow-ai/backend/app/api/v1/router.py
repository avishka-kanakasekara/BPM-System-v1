"""Shared API v1 router for all agents.

Aggregates Agent 4 process/approval/exception/audit/auth routes, Agent 3
allocation routes, and Agent 2 read/governance routes. Each agent router
keeps its own prefix. Mounted from main.py with prefix=/api/v1.
"""

from fastapi import APIRouter, Depends

from app.agents.agent2_execution.routers.governance import router as agent2_governance_router
from app.agents.agent2_execution.routers.read import router as agent2_read_router
from app.core.security import get_current_user
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

# Agent 2 — /api/v1/agent2/receipts, /kpis, /recommendations, /audit-logs.
# In the monolith these sit behind the shared Supabase JWT verification path,
# the same one every other agent's HTTP surface uses.
api_router.include_router(
    agent2_read_router, dependencies=[Depends(get_current_user)]
)
api_router.include_router(
    agent2_governance_router, dependencies=[Depends(get_current_user)]
)

# Agent 4
api_router.include_router(process_router)
api_router.include_router(approvals_router)
api_router.include_router(exceptions_router)
api_router.include_router(audit_router)
api_router.include_router(auth_router)

# Agent 3 — paths like /api/v1/agent3/allocations
api_router.include_router(agent3_router)
