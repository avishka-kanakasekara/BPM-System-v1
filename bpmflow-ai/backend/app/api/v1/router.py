"""API v1 router.

Only process routes are registered in this section. Later sections can include:
- task routes
- approval routes
- exception routes
- audit routes
- agent routes
"""

from fastapi import APIRouter

from app.api.v1.routes_process import router as process_router

api_router = APIRouter()
api_router.include_router(process_router)
