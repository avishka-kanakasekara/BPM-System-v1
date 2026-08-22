"""Tests for shared Supabase Auth JWT security."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.api.v1.deps import resolve_approver_id
from app.core import security as security_module
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    NOT_AUTHENTICATED_DETAIL,
    PROFILE_NOT_FOUND_DETAIL,
    require_roles,
    verify_supabase_access_token,
)
from app.main import app
from app.schemas.auth import CurrentUser

UTC = timezone.utc
TEST_SECRET = "test-supabase-jwt-secret-for-unit-tests-only"


def _encode(
    *,
    sub: str,
    exp_delta_seconds: int = 3600,
    secret: str = TEST_SECRET,
    extra: dict | None = None,
) -> str:
    now = datetime.now(tz=UTC)
    payload = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_delta_seconds)).timestamp()),
        "role": "authenticated",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    security_module.clear_jwks_cache()
    yield
    app.dependency_overrides.clear()
    security_module.clear_jwks_cache()


@pytest.fixture
def client():
    return TestClient(app)


def _user_row(*, user_id, role: str, email: str = "user@example.com"):
    return SimpleNamespace(
        id=user_id,
        email=email,
        full_name="Test User",
        role=role,
        department="Ops",
    )


def _override_db(user_row):
    session = AsyncMock()
    session.get = AsyncMock(return_value=user_row)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return session


def test_missing_authorization_header_returns_401(client) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == NOT_AUTHENTICATED_DETAIL


def test_invalid_bearer_token_returns_401(client) -> None:
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == NOT_AUTHENTICATED_DETAIL
    body = response.text
    assert TEST_SECRET not in body
    assert "Traceback" not in body


def test_malformed_token_returns_401(client) -> None:
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer abc.def"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == NOT_AUTHENTICATED_DETAIL


@pytest.mark.asyncio
async def test_expired_token_raises_authentication_error() -> None:
    user_id = str(uuid4())
    token = _encode(sub=user_id, exp_delta_seconds=-30)
    with pytest.raises(security_module.AuthenticationError):
        await verify_supabase_access_token(token)


def test_expired_token_returns_401(client) -> None:
    token = _encode(sub=str(uuid4()), exp_delta_seconds=-10)
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == NOT_AUTHENTICATED_DETAIL


def test_valid_jwt_unknown_profile_returns_403(client) -> None:
    user_id = uuid4()
    token = _encode(sub=str(user_id))
    _override_db(None)

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == PROFILE_NOT_FOUND_DETAIL


@pytest.mark.parametrize("role", ["requester", "approver", "admin"])
def test_valid_jwt_with_profile_returns_current_user(client, role) -> None:
    user_id = uuid4()
    token = _encode(sub=str(user_id))
    _override_db(_user_row(user_id=user_id, role=role, email=f"{role}@example.com"))

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user_id)
    assert body["role"] == role
    assert body["email"] == f"{role}@example.com"
    assert "password" not in body
    assert TEST_SECRET not in response.text
    assert settings.SUPABASE_SERVICE_ROLE_KEY not in response.text


def test_requester_rejected_by_require_roles_approver(client) -> None:
    user_id = uuid4()
    token = _encode(sub=str(user_id))
    _override_db(_user_row(user_id=user_id, role="requester"))

    response = client.get(
        "/api/v1/auth/approver-check",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


def test_approver_accepted_by_require_roles_approver(client) -> None:
    user_id = uuid4()
    token = _encode(sub=str(user_id))
    _override_db(_user_row(user_id=user_id, role="approver"))

    response = client.get(
        "/api/v1/auth/approver-check",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "approver"


def test_admin_accepted_by_require_roles_approver_admin(client) -> None:
    user_id = uuid4()
    token = _encode(sub=str(user_id))
    _override_db(_user_row(user_id=user_id, role="admin"))

    response = client.get(
        "/api/v1/auth/approver-check",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(user_id)
    assert response.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_jwt_user_id_always_comes_from_sub() -> None:
    user_id = uuid4()
    token = _encode(
        sub=str(user_id),
        extra={"user_id": str(uuid4()), "id": str(uuid4())},
    )
    claims = await verify_supabase_access_token(token)
    assert claims["sub"] == str(user_id)


def test_client_cannot_override_authenticated_user_id(client) -> None:
    real_id = uuid4()
    spoofed_id = uuid4()
    token = _encode(sub=str(real_id), extra={"user_id": str(spoofed_id)})
    session = _override_db(_user_row(user_id=real_id, role="requester"))

    response = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-User-Id": str(spoofed_id),
        },
        params={"user_id": str(spoofed_id)},
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(real_id)
    assert response.json()["id"] != str(spoofed_id)
    session.get.assert_awaited()
    assert session.get.await_args.args[1] == real_id


def test_no_secret_values_in_api_responses(client) -> None:
    user_id = uuid4()
    token = _encode(sub=str(user_id))
    _override_db(_user_row(user_id=user_id, role="admin"))

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    body = response.text
    assert response.status_code == 200
    assert TEST_SECRET not in body
    assert "your_supabase" not in body.lower()
    assert "service_role" not in body.lower()


def test_resolve_approver_id_uses_current_user() -> None:
    user = CurrentUser(
        id=uuid4(),
        email="approver@example.com",
        role="approver",
    )
    assert resolve_approver_id(user) == user.id


@pytest.mark.asyncio
async def test_require_roles_dependency_accepts_and_rejects() -> None:
    approver = CurrentUser(id=uuid4(), email="a@example.com", role="approver")
    requester = CurrentUser(id=uuid4(), email="r@example.com", role="requester")
    checker = require_roles("approver", "admin")

    accepted = await checker(current_user=approver)
    assert accepted.id == approver.id

    with pytest.raises(Exception) as exc_info:
        await checker(current_user=requester)
    assert getattr(exc_info.value, "status_code", None) == 403
