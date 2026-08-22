"""API v1 router. Agent 1 only — other agent and auth routes are not mounted yet."""

from fastapi import APIRouter

from app.api.v1.routes_agent1 import router as agent1_router

api_router = APIRouter()
api_router.include_router(agent1_router, prefix="/agent1", tags=["agent1"])
