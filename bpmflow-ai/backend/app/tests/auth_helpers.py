"""Shared auth overrides for API tests."""

from uuid import UUID, uuid4

from app.core.security import get_current_user
from app.main import app
from app.schemas.auth import CurrentUser


def override_current_user(
    *,
    role: str = "requester",
    user_id: UUID | None = None,
    email: str | None = None,
) -> UUID:
    """Override get_current_user with a fixed CurrentUser for API tests."""
    uid = user_id or uuid4()
    user = CurrentUser(
        id=uid,
        email=email or f"{role}@example.com",
        full_name=f"{role.title()} User",
        role=role,
        department="Ops",
    )

    async def _override() -> CurrentUser:
        return user

    app.dependency_overrides[get_current_user] = _override
    return uid


def bearer_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
