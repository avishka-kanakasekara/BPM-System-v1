"""Unified writer for public.audit_logs (BPM entity audit trail).

Agent 2 tool-decision logs use a separate table shape via agent2 security audit.
Process / approval / exception lifecycle events should use this module.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.supabase_rest import rest_insert, supabase_rest_configured
from app.models.audit import AuditLog

AUDIT_ENTITY_PROCESS = "process"


def utc_now() -> datetime:
    return datetime.now(UTC)


def bpm_audit_payload(
    *,
    entity_type: str,
    entity_id: UUID,
    action: str,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    performed_by: UUID | None = None,
) -> dict[str, Any]:
    """REST insert payload for audit_logs."""
    return {
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "action": action,
        "performed_by": str(performed_by) if performed_by else None,
        "old_values": old_values,
        "new_values": new_values,
    }


def bpm_audit_orm(
    *,
    entity_type: str,
    entity_id: UUID,
    action: str,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    performed_by: UUID | None = None,
    timestamp: datetime | None = None,
) -> AuditLog:
    """Construct an AuditLog ORM row (caller adds to session)."""
    return AuditLog(
        id=uuid4(),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        performed_by=performed_by,
        old_values=old_values,
        new_values=new_values,
        timestamp=timestamp or utc_now(),
    )


def write_bpm_audit_rest(
    *,
    entity_type: str,
    entity_id: UUID,
    action: str,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    performed_by: UUID | None = None,
) -> None:
    """Synchronous REST insert into audit_logs."""
    rest_insert(
        "audit_logs",
        bpm_audit_payload(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_values=old_values,
            new_values=new_values,
            performed_by=performed_by,
        ),
    )


async def write_bpm_audit(
    session: AsyncSession | None,
    *,
    entity_type: str,
    entity_id: UUID,
    action: str,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    performed_by: UUID | None = None,
    prefer_rest: bool = False,
) -> None:
    """Write audit_logs via Postgres session or REST (with REST fallback on PG failure)."""
    if prefer_rest or session is None:
        await asyncio.to_thread(
            write_bpm_audit_rest,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_values=old_values,
            new_values=new_values,
            performed_by=performed_by,
        )
        return

    try:
        session.add(
            bpm_audit_orm(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                old_values=old_values,
                new_values=new_values,
                performed_by=performed_by,
            )
        )
    except Exception:
        if supabase_rest_configured():
            await asyncio.to_thread(
                write_bpm_audit_rest,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                old_values=old_values,
                new_values=new_values,
                performed_by=performed_by,
            )
            return
        raise
