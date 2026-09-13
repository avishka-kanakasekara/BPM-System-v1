"""Authenticated user representation for API dependencies."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

ALLOWED_USER_ROLES = frozenset({"requester", "approver", "admin"})
UserRole = Literal["requester", "approver", "admin"]


class CurrentUser(BaseModel):
    """Authenticated BPMFlow user.

    id always comes from the verified JWT ``sub``.
    tenant_id, when present, comes only from verified JWT ``app_metadata`` —
    never from the request body or ``user_metadata``.
    """

    id: UUID
    email: str | None = None
    full_name: str | None = None
    role: str = Field(min_length=1)
    department: str | None = None
    tenant_id: UUID | None = None


class AuthRegisterRequest(BaseModel):
    """Local/dev registration payload (auto-confirms email).

    ``role`` is accepted only by the development register helper so local
    RBAC testing can create requester / approver / admin accounts. Production
    clients never reach this endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)
    role: UserRole = "requester"


class AuthRegisterResponse(BaseModel):
    id: UUID
    email: str
    confirmed: bool = True
    role: UserRole = "requester"


class AuthConfirmEmailRequest(BaseModel):
    """Confirm an existing Auth user by email (development only)."""

    email: EmailStr
