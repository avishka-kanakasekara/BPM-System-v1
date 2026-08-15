"""Shared API v1 router for all agents.

This module aggregates all agent-specific routers under the /api/v1 prefix.
Each agent's router is included exactly once with its own prefix.
"""

from fastapi import APIRouter

from app.api.v1.routes_agent3 import router as agent3_router

# Create the shared v1 API router
api_router = APIRouter(prefix="/api/v1")

# Include Agent 3 router with its own prefix
# This will result in paths like /api/v1/agent3/allocations
api_router.include_router(agent3_router)