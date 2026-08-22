"""
Shared persistence helpers so Agent 2 can write real process, task, and
workflow evidence to Supabase/Postgres whenever a session is available.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.database.ids import parse_uuid
from app.agents.agent2_execution.database.models import ProcessInstance, Task, WorkflowEvent

logger = logging.getLogger("agent_2.database.persistence")


async def ensure_process_instance(
    session: Optional[AsyncSession],
    process_id: str,
    *,
    title: str = "",
    process_type: str = "procurement",
    department: str = "",
    requester_email: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[ProcessInstance]:
    if session is None or not process_id:
        return None

    proc_uuid = parse_uuid(process_id)
    try:
        res = await session.execute(select(ProcessInstance).where(ProcessInstance.id == proc_uuid))
        row = res.scalar_one_or_none()
        if row:
            if metadata:
                merged = dict(row.metadata_json or {})
                merged.update(metadata)
                row.metadata_json = merged
            return row

        now = datetime.now(timezone.utc)
        # Canonical processes row. Agent 2 only sets its own columns:
        # execution_status is Agent 2's operational status; current_stage
        # stays untouched (Agent 4 / StateMachine owned).
        row = ProcessInstance(
            id=proc_uuid,
            process_type=process_type or "procurement",
            name=title or f"Process {process_id}",
            execution_status="IN_PROGRESS",
            department=department or None,
            requester_email=requester_email or None,
            metadata_json=metadata or {},
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()
        return row
    except Exception as exc:
        logger.warning(f"ensure_process_instance failed for {process_id!r}: {exc}")
        try:
            await session.rollback()
        except Exception:
            pass
        return None


async def ensure_task(
    session: Optional[AsyncSession],
    process_id: str,
    task_id: str,
    *,
    title: str = "",
    task_type: str = "AUTOMATED",
    assigned_role: str = "",
    assigned_to: str = "",
    sla_hours: float = 24.0,
    priority: str = "MEDIUM",
) -> Optional[Task]:
    if session is None or not task_id:
        return None

    await ensure_process_instance(session, process_id, title=title)
    task_uuid = parse_uuid(task_id)
    proc_uuid = parse_uuid(process_id)
    try:
        res = await session.execute(select(Task).where(Task.id == task_uuid))
        row = res.scalar_one_or_none()
        if row:
            return row

        now = datetime.now(timezone.utc)
        row = Task(
            id=task_uuid,
            process_id=proc_uuid,
            title=title or f"Task {task_id}",
            task_type=task_type or "AUTOMATED",
            status="IN_PROGRESS",
            assigned_role=assigned_role or None,
            assigned_to_email=assigned_to or None,
            sla_hours=sla_hours or 24.0,
            priority=priority or "MEDIUM",
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()
        return row
    except Exception as exc:
        logger.warning(f"ensure_task failed for {task_id!r}: {exc}")
        try:
            await session.rollback()
        except Exception:
            pass
        return None


async def merge_process_metadata(
    session: Optional[AsyncSession],
    process_id: str,
    patch: Dict[str, Any],
) -> None:
    if session is None or not process_id or not patch:
        return
    proc = await ensure_process_instance(session, process_id, metadata=patch)
    if proc is None:
        return
    merged = dict(proc.metadata_json or {})
    for key, value in patch.items():
        if isinstance(value, list) and isinstance(merged.get(key), list):
            merged[key] = list(merged[key]) + value
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    proc.metadata_json = merged
    proc.updated_at = datetime.now(timezone.utc)
    try:
        await session.commit()
    except Exception as exc:
        logger.warning(f"merge_process_metadata failed: {exc}")
        try:
            await session.rollback()
        except Exception:
            pass


async def record_workflow_event(
    session: Optional[AsyncSession],
    process_id: str,
    event_type: str,
    *,
    task_id: str = "",
    actor: str = "agent_2",
    metadata: Optional[Dict[str, Any]] = None,
    previous_state: str = "",
    new_state: str = "",
) -> Optional[WorkflowEvent]:
    if session is None or not process_id:
        return None
    await ensure_process_instance(session, process_id)
    event = WorkflowEvent(
        id=uuid.uuid4(),
        process_id=parse_uuid(process_id),
        task_id=parse_uuid(task_id) if task_id else None,
        event_type=event_type,
        actor=actor,
        agent="agent_2",
        timestamp=datetime.now(timezone.utc),
        metadata_json=metadata or {},
        previous_state=previous_state or None,
        new_state=new_state or None,
    )
    try:
        session.add(event)
        await session.commit()
        return event
    except Exception as exc:
        logger.warning(f"record_workflow_event failed: {exc}")
        try:
            await session.rollback()
        except Exception:
            pass
        return event
