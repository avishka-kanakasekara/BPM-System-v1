"""API v1 router.

Process, approval, exception, audit, and auth demo routes are registered.
Later sections can include:
- task routes
- agent routes
"""

from fastapi import APIRouter

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
