"""Auth routes: profile read plus development-friendly registration.

Production clients still authenticate with Supabase Auth JWTs. In
development, registration/confirmation helpers auto-confirm email so local
sign-in works when Supabase has mailer_autoconfirm disabled.
"""

from __future__ import annotations

from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.security import get_current_user, require_roles
from app.core.supabase_rest import rest_insert, rest_select, rest_update, supabase_rest_configured
from app.schemas.auth import (
    ALLOWED_USER_ROLES,
    AuthConfirmEmailRequest,
    AuthRegisterRequest,
    AuthRegisterResponse,
    CurrentUser,
    UserRole,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _dev_only() -> None:
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This auth helper is only available in development",
        )


def _admin_headers() -> dict[str, str]:
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase admin credentials are not configured",
        )
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _demo_tenant() -> str | None:
    raw = (settings.DEMO_TENANT_ID or "").strip()
    return raw or None


async def _find_user_id_by_email(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    email: str,
) -> tuple[str, dict] | None:
    base = settings.SUPABASE_URL.rstrip("/")
    filtered = await client.get(
        f"{base}/auth/v1/admin/users",
        headers=headers,
        params={"email": email, "page": 1, "per_page": 50},
    )
    candidates: list = []
    if filtered.is_success:
        payload = filtered.json() or {}
        if isinstance(payload, list):
            candidates = payload
        else:
            candidates = payload.get("users") or []
    for row in candidates:
        if str(row.get("email") or "").lower() == email:
            return str(row["id"]), row
    listed = await client.get(
        f"{base}/auth/v1/admin/users",
        headers=headers,
        params={"page": 1, "per_page": 200},
    )
    if not listed.is_success:
        return None
    for row in (listed.json() or {}).get("users") or []:
        if str(row.get("email") or "").lower() == email:
            return str(row["id"]), row
    return None


def _ensure_profile(
    user_id: str,
    email: str,
    full_name: str | None,
    role: UserRole = "requester",
) -> str:
    """Create or update public.users for development registration.

    Returns the role stored on the profile.
    """
    resolved: str = role if role in ALLOWED_USER_ROLES else "requester"
    if not supabase_rest_configured():
        return resolved
    existing = rest_select(
        "users",
        {"id": f"eq.{user_id}", "select": "id,role", "limit": "1"},
    )
    if existing:
        patch: dict = {"role": resolved, "email": email}
        if full_name:
            patch["full_name"] = full_name
        rest_update("users", {"id": f"eq.{user_id}"}, patch)
        return resolved
    rest_insert(
        "users",
        {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "role": resolved,
        },
    )
    return resolved



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


@router.post("/register", response_model=AuthRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_user(payload: AuthRegisterRequest) -> AuthRegisterResponse:
    """Create a confirmed Supabase user for local development sign-in.

    Supabase projects often leave email confirmation enabled. Without this
    helper, UI sign-up creates an unconfirmed account and sign-in fails with
    ``email_not_confirmed``. Production must use the normal Supabase flow.
    """
    _dev_only()
    headers = _admin_headers()
    base = settings.SUPABASE_URL.rstrip("/")
    email = str(payload.email).strip().lower()
    body: dict = {
        "email": email,
        "password": payload.password,
        "email_confirm": True,
        "user_metadata": {},
    }
    if payload.full_name and payload.full_name.strip():
        body["user_metadata"]["full_name"] = payload.full_name.strip()
    tenant = _demo_tenant()
    if tenant:
        body["app_metadata"] = {"tenant_id": tenant}

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        response = await client.post(
            f"{base}/auth/v1/admin/users",
            headers=headers,
            json=body,
        )
        if response.status_code in {400, 422} and "already" in response.text.lower():
            # User exists — confirm email so they can sign in.
            found = await _find_user_id_by_email(client, headers, email)
            if found is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email already exists",
                )
            user_id, match = found
            patch = await client.put(
                f"{base}/auth/v1/admin/users/{user_id}",
                headers=headers,
                json={
                    "email_confirm": True,
                    "password": payload.password,
                    **(
                        {"app_metadata": {"tenant_id": tenant}}
                        if tenant and not (match.get("app_metadata") or {}).get("tenant_id")
                        else {}
                    ),
                },
            )
            if not patch.is_success:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Could not confirm existing auth user",
                )
            full_name = payload.full_name.strip() if payload.full_name else None
            stored_role = _ensure_profile(user_id, email, full_name, payload.role)
            return AuthRegisterResponse(
                id=UUID(user_id),
                email=email,
                confirmed=True,
                role=stored_role,  # type: ignore[arg-type]
            )

        if not response.is_success:
            detail = "Could not create auth user"
            try:
                err = response.json()
                detail = str(err.get("msg") or err.get("message") or detail)
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=detail,
            )
        created = response.json()
        user_id = str(created["id"])
        email = str(created.get("email") or payload.email).strip().lower()
        full_name = payload.full_name.strip() if payload.full_name else None
        stored_role = _ensure_profile(user_id, email, full_name, payload.role)
        return AuthRegisterResponse(
            id=UUID(user_id),
            email=email,
            confirmed=True,
            role=stored_role,  # type: ignore[arg-type]
        )


@router.post("/confirm-email", status_code=status.HTTP_200_OK)
async def confirm_email(payload: AuthConfirmEmailRequest) -> dict:
    """Confirm an unconfirmed Auth email in development (no secrets returned)."""
    _dev_only()
    headers = _admin_headers()
    base = settings.SUPABASE_URL.rstrip("/")
    email = str(payload.email).strip().lower()

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        found = await _find_user_id_by_email(client, headers, email)
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No account found for that email",
            )
        user_id, match = found
        body: dict = {"email_confirm": True}
        tenant = _demo_tenant()
        if tenant and not (match.get("app_metadata") or {}).get("tenant_id"):
            body["app_metadata"] = {"tenant_id": tenant}
        patched = await client.put(
            f"{base}/auth/v1/admin/users/{user_id}",
            headers=headers,
            json=body,
        )
        if not patched.is_success:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not confirm email",
            )
        meta = match.get("user_metadata") if isinstance(match.get("user_metadata"), dict) else {}
        _ensure_profile(user_id, email, meta.get("full_name") if isinstance(meta, dict) else None)
        return {"ok": True, "email": email, "confirmed": True}
