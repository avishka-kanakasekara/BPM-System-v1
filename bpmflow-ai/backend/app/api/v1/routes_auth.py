"""Protected auth demonstration routes for Section 12A."""

from fastapi import APIRouter, Depends

from app.core.security import get_current_user, require_roles
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=CurrentUser)
async def read_current_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Return the authenticated public.users profile."""
    return current_user


@router.get("/approver-check", response_model=CurrentUser)
async def approver_check(
    current_user: CurrentUser = Depends(require_roles("approver", "admin")),
) -> CurrentUser:
    """Demonstrate role authorization for approver/admin only."""
    return current_user
