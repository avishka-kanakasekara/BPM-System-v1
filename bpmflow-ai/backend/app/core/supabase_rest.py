"""Supabase PostgREST client used when the Postgres pooler is unreachable."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from app.core.config import settings
from app.core.logging import get_logger

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
    # trust_env=False: ignore HTTP(S)_PROXY so local/dev proxies cannot break
    # Supabase HTTPS calls (otherwise health/REST fail with ProxyError 403).
    return httpx.Client(
        base_url=settings.SUPABASE_URL.rstrip("/"),
        timeout=30.0,
        headers=_headers(),
        trust_env=False,
    )


def _raise_for_status(response: httpx.Response, action: str) -> None:
    if response.is_success:
        return
    logger.error(
        "supabase_rest_error",
        extra={"action": action, "status": response.status_code, "body": response.text[:500]},
    )
    response.raise_for_status()


def rest_insert(table: str, row: dict[str, Any]) -> dict[str, Any]:
    with _client() as client:
        response = client.post(f"/rest/v1/{table}", json=row)
        _raise_for_status(response, f"insert {table}")
        data = response.json()
        if isinstance(data, list):
            return data[0] if data else row
        return data if isinstance(data, dict) else row


def rest_select(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    with _client() as client:
        response = client.get(f"/rest/v1/{table}", params=params)
        _raise_for_status(response, f"select {table}")
        data = response.json()
        return data if isinstance(data, list) else []


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


def ping_rest() -> bool:
    if not supabase_rest_configured():
        return False
    try:
        with _client() as client:
            response = client.get("/rest/v1/processes", params={"select": "id", "limit": "1"})
            return response.is_success
    except Exception:
        logger.exception("supabase_rest_ping_failed")
        return False
