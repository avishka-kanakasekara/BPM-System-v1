"""
Agent 2 — Audit Logging Subsystem

Enforces Rule #7 Non-Negotiable invariant:
Every decision — allowed or blocked — gets an audit log entry with actor, action, allowed, reason, payload, and timestamp.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.database.models import AuditLog

logger = logging.getLogger("agent_2.security.audit")


async def log_audit_event(
    session: Optional[AsyncSession],
    actor: str,
    action: str,
    allowed: bool,
    reason: str,
    agent: str = "agent_2",
    payload: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """
    Write a structured audit log entry to the audit_logs table.

    :param session: Active SQLAlchemy AsyncSession (optional)
    :param actor: Identifier of actor taking or requesting action (e.g. agent_2, user_id, agent_4)
    :param action: Action or tool name (e.g. create_po_draft, approve_payment)
    :param allowed: True if decision allowed action; False if blocked
    :param reason: Rationale for decision (e.g. "Action permitted by policy", "Action forbidden by Rule #4")
    :param agent: Agent identifier (default "agent_2")
    :param payload: Optional parameters or context dictionary
    :return: Constructed AuditLog ORM record
    """
    log_entry = AuditLog(
        id=uuid.uuid4(),
        entity_type="agent2_decision",
        actor=actor,
        agent=agent,
        action=action,
        allowed=allowed,
        reason=reason,
        payload=payload or {},
        timestamp=datetime.now(timezone.utc),
    )

    log_level = logging.INFO if allowed else logging.WARNING
    logger.log(
        log_level,
        f"AUDIT LOG [{ 'ALLOWED' if allowed else 'BLOCKED' }]: actor={actor} action={action} reason={reason!r}",
    )

    if session is not None:
        session.add(log_entry)
        await session.commit()

    return log_entry
