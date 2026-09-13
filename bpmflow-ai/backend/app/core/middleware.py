"""Production HTTP middleware: correlation, rate limits, request size, shutdown drain."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core import shutdown as shutdown_state
from app.core.config import settings
from app.core.logging import correlation_id_var
from app.core.rate_limit import RateLimitExceeded, SlidingWindowRateLimiter

_auth_limiter = SlidingWindowRateLimiter(
    max_requests=settings.RATE_LIMIT_AUTH_PER_MINUTE,
    window_seconds=60.0,
)
_upload_limiter = SlidingWindowRateLimiter(
    max_requests=settings.RATE_LIMIT_UPLOAD_PER_MINUTE,
    window_seconds=60.0,
)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return str(forwarded.split(",")[0].strip())
    if request.client and request.client.host:
        return str(request.client.host)
    return "unknown"


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Propagate X-Correlation-ID (or generate) into logging context."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming = request.headers.get("x-correlation-id") or request.headers.get("x-request-id")
        correlation_id = (incoming or str(uuid.uuid4())).strip()
        token = correlation_id_var.set(correlation_id)
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class RequestGuardMiddleware(BaseHTTPMiddleware):
    """Reject oversize bodies and requests during shutdown drain."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not shutdown_state.accepting_requests() and request.url.path not in {
            "/health/live",
            "/health/ready",
            "/health",
            "/health/deps",
        }:
            return JSONResponse(
                status_code=503,
                content={"detail": "Server is shutting down"},
            )

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > settings.max_request_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": f"Request body exceeds {settings.MAX_REQUEST_MB} MB limit"},
                    )
            except ValueError:
                pass

        shutdown_state.increment_in_flight()
        try:
            return await call_next(request)
        finally:
            shutdown_state.decrement_in_flight()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit auth and upload endpoints per client IP."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        method = request.method.upper()
        client = _client_key(request)

        try:
            if path.startswith("/api/v1/auth") and method in {"POST", "PUT", "PATCH"}:
                _auth_limiter.check(f"auth:{client}")
            if path.endswith("/discover") and method == "POST":
                _upload_limiter.check(f"upload:{client}")
        except RateLimitExceeded as exc:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Try again later."},
                headers={"Retry-After": str(int(max(1, exc.retry_after_seconds)))},
            )

        return await call_next(request)
