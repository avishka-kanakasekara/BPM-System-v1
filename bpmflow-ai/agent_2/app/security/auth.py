"""
Agent 2 — Authentication Subsystem

Provides JWT issuing and validation for inbound requests from Agent 4 (Orchestrator).
Uses a shared secret configured in app.config.settings.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

# JWT configuration
ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = 60


def get_jwt_secret() -> str:
    """Return configured secret key for JWT signing and verification."""
    secret = settings.AGENT4_API_KEY
    if not secret:
        # Fallback secret for local development / testing
        secret = "dev_shared_jwt_secret_agent2_bpmflow_ai"
    return secret


def create_access_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """
    Issue a signed JWT access token for inter-agent API calls.

    :param data: Payload dictionary to include in JWT claims (e.g. {"sub": "agent_4", "role": "orchestrator"})
    :param expires_delta: Optional token lifetime duration
    :return: Encoded JWT token string
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=DEFAULT_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": now, "iss": "bpmflow-ai"})
    secret = get_jwt_secret()
    return jwt.encode(to_encode, secret, algorithm=ALGORITHM)


def verify_access_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode a JWT token string.

    :param token: Encoded JWT token string
    :return: Decoded claims payload dictionary
    :raises HTTPException: 401 Unauthorized if invalid or expired
    """
    secret = get_jwt_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authorization token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


security_bearer = HTTPBearer(auto_error=False)


def get_current_agent_caller(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> Dict[str, Any]:
    """
    FastAPI dependency to enforce Bearer JWT authentication on endpoints.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_access_token(credentials.credentials)
