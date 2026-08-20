"""Authenticated user representation for API dependencies."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


ALLOWED_USER_ROLES = frozenset({"requester", "approver", "admin"})


class CurrentUser(BaseModel):
    """Authenticated BPMFlow user. id always comes from JWT sub."""

    id: UUID
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str = Field(min_length=1)
    department: Optional[str] = None
