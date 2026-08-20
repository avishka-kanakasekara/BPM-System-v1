"""API v1 router.

Process and approval routes are registered. Later sections can include:
- task routes
- exception routes
- audit routes
- agent routes
"""

from fastapi import APIRouter

from app.api.v1.routes_approvals import router as approvals_router
from app.api.v1.routes_process import router as process_router

api_router = APIRouter()
api_router.include_router(process_router)
api_router.include_router(approvals_router)
