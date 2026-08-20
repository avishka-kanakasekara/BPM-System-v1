"""Supabase Auth JWT validation and FastAPI auth dependencies.

Supabase Auth is the identity provider. FastAPI validates access tokens and
loads matching public.users profiles. No custom password/login flows.
"""

from __future__ import annotations

import time
from typing import Callable
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import ALLOWED_USER_ROLES, CurrentUser

bearer_scheme = HTTPBearer(auto_error=False)

NOT_AUTHENTICATED_DETAIL = "Not authenticated"
PROFILE_NOT_FOUND_DETAIL = "User profile not found"
FORBIDDEN_DETAIL = "Insufficient permissions"

# JWKS cache: (fetched_at_epoch, jwks_payload)
_jwks_cache: tuple[float, dict] | None = None
_JWKS_CACHE_TTL_SECONDS = 300


class AuthenticationError(Exception):
    """Raised when a Bearer token cannot be validated."""


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=NOT_AUTHENTICATED_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(detail: str = FORBIDDEN_DETAIL) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def supabase_jwks_url() -> str:
    """Build JWKS URL from configured SUPABASE_URL. No hardcoded project URLs."""
    base = (settings.SUPABASE_URL or "").rstrip("/")
    if not base:
        raise AuthenticationError("SUPABASE_URL is not configured")
    return f"{base}/auth/v1/.well-known/jwks.json"


def expected_issuer() -> str | None:
    base = (settings.SUPABASE_URL or "").rstrip("/")
    if not base:
        return None
    return f"{base}/auth/v1"


async def fetch_jwks(*, force_refresh: bool = False) -> dict:
    """Fetch and cache Supabase JWKS public keys."""
    global _jwks_cache
    now = time.time()
    if (
        not force_refresh
        and _jwks_cache is not None
        and (now - _jwks_cache[0]) < _JWKS_CACHE_TTL_SECONDS
    ):
        return _jwks_cache[1]

    url = supabase_jwks_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        raise AuthenticationError("Unable to fetch signing keys") from exc

    if not isinstance(payload, dict) or "keys" not in payload:
        raise AuthenticationError("Invalid signing key response")

    _jwks_cache = (now, payload)
    return payload


def clear_jwks_cache() -> None:
    """Test helper to reset JWKS cache."""
    global _jwks_cache
    _jwks_cache = None


def _rsa_or_ec_key_from_jwk(jwk_data: dict) -> dict:
    return jwk_data


async def _decode_with_jwks(token: str, header: dict) -> dict:
    kid = header.get("kid")
    alg = header.get("alg")
    if not kid or not alg:
        raise AuthenticationError("Malformed token")

    jwks = await fetch_jwks()
    keys = jwks.get("keys") or []
    matching = next((key for key in keys if key.get("kid") == kid), None)
    if matching is None:
        jwks = await fetch_jwks(force_refresh=True)
        keys = jwks.get("keys") or []
        matching = next((key for key in keys if key.get("kid") == kid), None)
    if matching is None:
        raise AuthenticationError("Unknown signing key")

    options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_aud": False,
        "verify_iss": False,
    }
    claims = jwt.decode(
        token,
        _rsa_or_ec_key_from_jwk(matching),
        algorithms=[alg],
        options=options,
    )
    _validate_issuer(claims)
    return claims


def _decode_with_secret(token: str, header: dict) -> dict:
    secret = settings.SUPABASE_JWT_SECRET or ""
    if not secret:
        raise AuthenticationError("JWT secret is not configured")
    alg = header.get("alg") or "HS256"
    if alg != "HS256":
        raise AuthenticationError("Unsupported signing algorithm")

    options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_aud": False,
        "verify_iss": False,
    }
    claims = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options=options,
    )
    _validate_issuer(claims)
    return claims


def _validate_issuer(claims: dict) -> None:
    """When an issuer claim is present, it must match SUPABASE_URL/auth/v1."""
    expected = expected_issuer()
    token_iss = claims.get("iss")
    if expected and token_iss and token_iss != expected:
        raise AuthenticationError("Invalid token")


async def verify_supabase_access_token(token: str) -> dict:
    """Validate a Supabase access JWT and return claims.

    Verification order:
    1. Asymmetric JWKS (preferred) when token alg is ES256/RS256 and SUPABASE_URL is set
    2. Symmetric HS256 using optional SUPABASE_JWT_SECRET for legacy projects
    """
    if not token or not token.strip():
        raise AuthenticationError("Missing token")

    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise AuthenticationError("Malformed token") from exc

    alg = header.get("alg")
    try:
        if alg in {"ES256", "RS256"}:
            claims = await _decode_with_jwks(token, header)
        elif alg == "HS256":
            claims = _decode_with_secret(token, header)
        else:
            # Prefer JWKS path when algorithm is unknown but kid exists.
            if header.get("kid") and settings.SUPABASE_URL:
                claims = await _decode_with_jwks(token, header)
            elif settings.SUPABASE_JWT_SECRET:
                claims = _decode_with_secret(token, header)
            else:
                raise AuthenticationError("Unsupported token")
    except ExpiredSignatureError as exc:
        raise AuthenticationError("Expired token") from exc
    except JWTError as exc:
        raise AuthenticationError("Invalid token") from exc

    sub = claims.get("sub")
    if not sub:
        raise AuthenticationError("Invalid token")
    try:
        UUID(str(sub))
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("Invalid token") from exc

    return claims


async def load_user_profile(db: AsyncSession, user_id: UUID) -> CurrentUser:
    """Load public.users by id. Does not create profiles."""
    try:
        row = await db.get(User, user_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc

    if row is None:
        raise _forbidden(PROFILE_NOT_FOUND_DETAIL)

    role = row.role or ""
    if role not in ALLOWED_USER_ROLES:
        raise _forbidden(PROFILE_NOT_FOUND_DETAIL)

    return CurrentUser(
        id=row.id,
        email=row.email,
        full_name=row.full_name,
        role=role,
        department=row.department,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Authenticate via Bearer token and return the public.users profile."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _unauthorized()

    try:
        claims = await verify_supabase_access_token(credentials.credentials)
    except AuthenticationError:
        raise _unauthorized() from None

    user_id = UUID(str(claims["sub"]))
    return await load_user_profile(db, user_id)


def require_roles(*roles: str) -> Callable:
    """Authorization dependency: authenticated user must have one of roles."""
    allowed = frozenset(roles)
    unknown = allowed - ALLOWED_USER_ROLES
    if unknown:
        raise ValueError(f"Unsupported roles in require_roles: {sorted(unknown)}")

    async def _dependency(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.role not in allowed:
            raise _forbidden()
        return current_user

    return _dependency
