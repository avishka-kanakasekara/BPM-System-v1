"""Supabase PostgREST client used when the Postgres pooler is unreachable."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from app.core.config import settings
from app.core.http_client import call_with_circuit, external_timeout_seconds
from app.core.logging import get_logger
from app.core.redaction import redact_text

logger = get_logger(__name__)


def supabase_rest_configured() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)


def _headers() -> dict[str, str]:
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _client() -> httpx.Client:
    if not supabase_rest_configured():
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return httpx.Client(
        base_url=settings.SUPABASE_URL.rstrip("/"),
        timeout=external_timeout_seconds(),
        headers=_headers(),
        trust_env=False,
    )


def _raise_for_status(response: httpx.Response, action: str) -> None:
    if response.is_success:
        return
    logger.error(
        "supabase_rest_error",
        extra={
            "action": action,
            "status": response.status_code,
            "body": redact_text(response.text[:500]),
        },
    )
    response.raise_for_status()


def rest_insert(table: str, row: dict[str, Any]) -> dict[str, Any]:
    def _call() -> dict[str, Any]:
        with _client() as client:
            response = client.post(f"/rest/v1/{table}", json=row)
            _raise_for_status(response, f"insert {table}")
            data = response.json()
            if isinstance(data, list):
                return data[0] if data else row
            return data if isinstance(data, dict) else row

    return call_with_circuit("supabase_rest", _call)


def rest_update(table: str, match: dict[str, str], patch: dict[str, Any]) -> dict[str, Any]:
    """PATCH rows matching PostgREST filters (e.g. id=eq.<uuid>)."""

    def _call() -> dict[str, Any]:
        with _client() as client:
            response = client.patch(f"/rest/v1/{table}", params=match, json=patch)
            _raise_for_status(response, f"update {table}")
            data = response.json()
            if isinstance(data, list):
                return data[0] if data else patch
            return data if isinstance(data, dict) else patch

    return call_with_circuit("supabase_rest", _call)


def rest_select(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    def _call() -> list[dict[str, Any]]:
        with _client() as client:
            response = client.get(f"/rest/v1/{table}", params=params)
            _raise_for_status(response, f"select {table}")
            data = response.json()
            return data if isinstance(data, list) else []

    return call_with_circuit("supabase_rest", _call)


def record_ingestion_event(
    *,
    file_id: UUID,
    actor: str,
    event_type: str,
    detail: dict[str, Any],
) -> None:
    rest_insert(
        "audit_logs",
        {
            "entity_type": "document",
            "entity_id": str(file_id),
            "action": event_type,
            "new_values": {**detail, "actor": actor},
        },
    )


def ping_rest(*, timeout_seconds: float = 3.0) -> bool:
    if not supabase_rest_configured():
        return False
    try:
        with httpx.Client(
            base_url=settings.SUPABASE_URL.rstrip("/"),
            timeout=timeout_seconds,
            headers=_headers(),
            trust_env=False,
        ) as client:
            response = client.get("/rest/v1/processes", params={"select": "id", "limit": "1"})
            return response.is_success
    except Exception:
        logger.exception("supabase_rest_ping_failed")
        return False


def use_supabase_rest_fallback() -> bool:
    """True when persistence is in degraded REST mode."""
    from app.core.persistence import PersistenceMode, get_effective_mode

    return get_effective_mode() == PersistenceMode.REST and supabase_rest_configured()
