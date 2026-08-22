<<<<<<< HEAD
"""Supabase Auth JWT validation and FastAPI auth dependencies.

Supabase Auth is the identity provider. FastAPI validates access tokens and
loads matching public.users profiles. No custom password/login flows.
=======
"""Supabase JWT verification and trusted principal extraction.

This module provides secure JWT verification for Supabase access tokens using
the JWKS (JSON Web Key Set) endpoint. It follows the safest available approach:

- Verifies token signature against Supabase JWKS endpoint
- Validates algorithm (rejects alg=none)
- Validates issuer exactly
- Validates expiration and other standard claims
- Extracts tenant_id from verified app_metadata only
- Never trusts unverified payloads
- Never exposes secrets or raw tokens in errors/logs

TENANT SOURCE:
- tenant_id MUST come from app_metadata.tenant_id (administratively controlled)
- user_metadata is NEVER used for authorization (user-editable)
- Missing/malformed tenant claim fails closed
- JWT claim staleness is a documented limitation until token refresh

SECURITY RULES:
- Never decode a JWT without verifying it
- Never trust user_metadata for authorization
- Never expose access tokens, API keys, DB URLs, passwords or JWT payloads
- Never use Supabase service-role keys in the frontend
>>>>>>> origin/developer-branch
"""

from __future__ import annotations

<<<<<<< HEAD
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
=======
import asyncio
import json
from datetime import datetime, timezone
from functools import lru_cache
from typing import Dict, Optional, Set, Tuple
from uuid import UUID

import httpx
from fastapi import HTTPException, Request, status
from jose import jwk, jwt
from jose.exceptions import ExpiredSignatureError, JWTError, JWTClaimsError
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


# ============================================================================
# Verified Principal Model
# ============================================================================


class VerifiedPrincipal(BaseModel):
    """Verified principal from Supabase JWT.

    All fields are extracted from verified JWT claims only.

    Attributes:
        user_id: UUID from verified 'sub' claim
        tenant_id: UUID from verified app_metadata.tenant_id
        roles: Frozen set of role strings from verified claims
        token_role: Token role from 'role' claim (e.g., 'authenticated', 'anon')
        session_id: Optional session ID from claims
        expires_at: Token expiration datetime

    Security:
        - All fields come from verified JWT claims
        - tenant_id comes from app_metadata only (administratively controlled)
        - user_metadata is never used for authorization
    """

    user_id: UUID = Field(..., description="User ID from verified 'sub' claim")
    tenant_id: UUID = Field(..., description="Tenant ID from verified app_metadata.tenant_id")
    roles: frozenset[str] = Field(default_factory=frozenset, description="User roles from verified claims")
    token_role: str = Field(default="authenticated", description="Token role from 'role' claim")
    session_id: Optional[UUID] = Field(None, description="Session ID from claims")
    expires_at: datetime = Field(..., description="Token expiration datetime")

    @field_validator("expires_at", mode="after")
    @classmethod
    def validate_expiration(cls, value: datetime) -> datetime:
        """Ensure expiration is timezone-aware."""
        if value.tzinfo is None:
            # Assume UTC if no timezone
            return value.replace(tzinfo=timezone.utc)
        return value


# ============================================================================
# JWKS Caching
# ============================================================================


class JWKSCache:
    """Thread-safe JWKS cache with bounded expiry and rotation support.

    Caches JWKS from Supabase to avoid repeated HTTP requests.
    Cache entries expire after a configurable TTL.
    """

    def __init__(self, ttl_seconds: int = 300):
        """Initialize JWKS cache.

        Args:
            ttl_seconds: Time-to-live for cached JWKS in seconds (default: 5 minutes)
        """
        self._cache: Dict[str, Tuple[dict, datetime]] = {}
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    async def get_jwks(self, jwks_url: str) -> dict:
        """Get JWKS from cache or fetch fresh.

        Args:
            jwks_url: The JWKS endpoint URL

        Returns:
            The JWKS JSON object

        Raises:
            HTTPException: If JWKS fetch fails
        """
        async with self._lock:
            # Check cache
            if jwks_url in self._cache:
                jwks_data, cached_at = self._cache[jwks_url]
                age = (datetime.now(timezone.utc) - cached_at).total_seconds()
                if age < self._ttl:
                    return jwks_data

            # Fetch fresh JWKS
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(jwks_url)
                    response.raise_for_status()
                    jwks_data = response.json()

                # Cache the result
                self._cache[jwks_url] = (jwks_data, datetime.now(timezone.utc))
                return jwks_data

            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error_code": "JWKS_FETCH_FAILED",
                        "message": "Failed to fetch JWT verification keys",
                        "retryable": True,
                    },
                ) from exc


# Global JWKS cache instance
_jwks_cache = JWKSCache()


# ============================================================================
# JWT Verification
# ============================================================================


def _get_jwks_url(supabase_url: str) -> str:
    """Construct JWKS URL from Supabase URL.

    Args:
        supabase_url: The Supabase project URL

    Returns:
        The JWKS endpoint URL
    """
    base_url = supabase_url.rstrip("/")
    if base_url.endswith("/auth/v1"):
        return f"{base_url}/.well-known/jwks.json"
    return f"{base_url}/auth/v1/.well-known/jwks.json"


def _get_expected_issuer(supabase_url: str) -> str:
    """Construct expected issuer from Supabase URL.

    Args:
        supabase_url: The Supabase project URL

    Returns:
        The expected issuer string
    """
    base_url = supabase_url.rstrip("/")
    if base_url.endswith("/auth/v1"):
        return base_url
    return f"{base_url}/auth/v1"


async def verify_supabase_token(token: str) -> VerifiedPrincipal:
    """Verify a Supabase access token and extract verified principal.

    This function:
    - Fetches JWKS from Supabase (cached)
    - Verifies token signature against JWKS
    - Validates algorithm (rejects alg=none)
    - Validates issuer exactly
    - Validates expiration, nbf, and other standard claims
    - Extracts tenant_id from app_metadata only
    - Fails closed on any validation error

    Args:
        token: The Supabase access token (Bearer token)

    Returns:
        VerifiedPrincipal with verified claims

    Raises:
        HTTPException: 401 if token is invalid/expired/malformed
        HTTPException: 403 if tenant claim is missing/malformed
        HTTPException: 503 if JWKS fetch fails
    """
    if not settings.SUPABASE_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "SUPABASE_NOT_CONFIGURED",
                "message": "Supabase URL not configured",
                "retryable": False,
            },
        )

    # Get JWKS URL and expected issuer
    jwks_url = _get_jwks_url(settings.SUPABASE_URL)
    expected_issuer = _get_expected_issuer(settings.SUPABASE_URL)

    try:
        # Fetch JWKS (cached)
        jwks_data = await _jwks_cache.get_jwks(jwks_url)

        # Parse JWKS
        jwks_keys = jwks_data.get("keys", [])
        if not jwks_keys:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error_code": "JWKS_NO_KEYS",
                    "message": "No JWT verification keys available",
                    "retryable": True,
                },
            )

        # Build key dictionary for jose
        keys = {}
        for key_data in jwks_keys:
            key_id = key_data.get("kid")
            if key_id:
                keys[key_id] = jwk.construct(key_data)

        # Decode and verify token
        # jose.decode automatically verifies signature, exp, nbf, iat
        # We explicitly validate issuer and algorithm
        header = jwt.get_unverified_header(token)
        key_id = header.get("kid")

        if not key_id or key_id not in keys:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "INVALID_TOKEN",
                    "message": "Invalid token signature",
                    "retryable": False,
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Verify header algorithm before decoding
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")

        # Enforce ES256 only for this project (matches Supabase project configuration)
        # Do not trust header alone - must match expected algorithm
        allowed_algorithms = ["ES256"]
        if alg not in allowed_algorithms:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "INVALID_ALGORITHM",
                    "message": f"Token algorithm '{alg}' not allowed. Only ES256 is supported.",
                    "retryable": False,
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        claims = jwt.decode(
            token,
            keys[key_id],
            algorithms=allowed_algorithms,
            audience="authenticated",  # Supabase uses "authenticated" as audience
            issuer=expected_issuer,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": True,  # Enforce audience validation
                "verify_iss": True,
            },
        )

        # Extract required claims
        sub = claims.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "INVALID_TOKEN",
                    "message": "Token missing required 'sub' claim",
                    "retryable": False,
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Extract tenant_id from app_metadata only
        app_metadata = claims.get("app_metadata", {})
        tenant_id_str = app_metadata.get("tenant_id")

        if not tenant_id_str:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": "TENANT_CLAIM_MISSING",
                    "message": "Tenant claim not found in app_metadata",
                    "retryable": False,
                },
            )

        try:
            tenant_id = UUID(tenant_id_str)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": "TENANT_CLAIM_INVALID",
                    "message": "Tenant claim is not a valid UUID",
                    "retryable": False,
                },
            )

        # Extract user_id from sub
        try:
            user_id = UUID(sub)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "INVALID_TOKEN",
                    "message": "Invalid user ID in token",
                    "retryable": False,
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Extract roles from verified claims
        # Roles can come from various claim locations depending on Supabase configuration
        role_claims = claims.get("role", "authenticated")
        user_role = str(role_claims)

        # Extract additional roles if present
        roles_set: Set[str] = {user_role}
        if "user_roles" in claims:
            if isinstance(claims["user_roles"], list):
                roles_set.update(claims["user_roles"])
            elif isinstance(claims["user_roles"], str):
                roles_set.add(claims["user_roles"])

        # Extract session_id if present
        session_id = None
        if "session_id" in claims:
            try:
                session_id = UUID(claims["session_id"])
            except (ValueError, AttributeError):
                pass  # Session ID is optional

        # Extract expiration
        exp = claims.get("exp")
        if exp:
            expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
        else:
            # Default to 1 hour from now if not present (shouldn't happen with valid JWT)
            expires_at = datetime.now(timezone.utc).replace(microsecond=0)

        return VerifiedPrincipal(
            user_id=user_id,
            tenant_id=tenant_id,
            roles=frozenset(roles_set),
            token_role=user_role,
            session_id=session_id,
            expires_at=expires_at,
        )

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "TOKEN_EXPIRED",
                "message": "Token has expired",
                "retryable": False,
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (JWTError, JWTClaimsError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "INVALID_TOKEN",
                "message": "Invalid token",
                "retryable": False,
            },
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ============================================================================
# FastAPI Dependency
# ============================================================================


async def get_verified_principal(request: Request) -> VerifiedPrincipal:
    """FastAPI dependency to extract verified principal from Authorization header.

    This dependency:
    - Extracts Bearer token from Authorization header
    - Verifies token signature and claims
    - Returns VerifiedPrincipal with tenant_id from app_metadata
    - Fails closed with 401/403 on any error

    Args:
        request: The FastAPI request object

    Returns:
        VerifiedPrincipal with verified claims

    Raises:
        HTTPException: 401 if missing/invalid token
        HTTPException: 403 if tenant claim missing/invalid
        HTTPException: 503 if JWKS fetch fails
    """
    authorization = request.headers.get("Authorization")

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "MISSING_AUTHORIZATION",
                "message": "Authorization header required",
                "retryable": False,
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "INVALID_AUTHORIZATION_FORMAT",
                "message": "Authorization header must be 'Bearer <token>'",
                "retryable": False,
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[7:]  # Remove "Bearer " prefix

    return await verify_supabase_token(token)
>>>>>>> origin/developer-branch
