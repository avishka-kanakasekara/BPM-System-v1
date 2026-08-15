"""
Agent 2 — Context Engine (PERCEIVE + UNDERSTAND Nodes 1 & 2)

Loads process instance state, active task parameters, SLA details, and organizational policy
from the database into a structured ProcessContext object.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ProcessInstance, Task
from app.llm.schemas import AgentMessage


@dataclass
class ProcessContext:
    process_id: str
    task_id: str
    process_title: str
    process_type: str
    task_title: str
    task_type: str
    assigned_role: str
    assigned_to: str
    priority: str
    sla_hours: float
    elapsed_hours: float
    status: str
    department: str
    requester_email: str
    metadata: Dict[str, Any] = field(default_factory=dict)


async def perceive_context(
    session: Optional[AsyncSession], message: AgentMessage
) -> ProcessContext:
    """
    PERCEIVE & UNDERSTAND: Load process/task context from database given an AgentMessage.

    :param session: Active AsyncSession (optional)
    :param message: Incoming AgentMessage
    :return: Populated ProcessContext object
    """
    proc_id = message.process_id
    payload = message.payload or {}
    task_id = payload.get("task_id", "")

    # Default fallback context
    ctx = ProcessContext(
        process_id=proc_id,
        task_id=task_id or str(uuid.uuid4()),
        process_title=f"Procurement Process ({proc_id})",
        process_type=payload.get("process_type", "procurement"),
        task_title=payload.get("task_title", "Process Task"),
        task_type=payload.get("task_type", "AUTOMATED"),
        assigned_role=payload.get("assigned_role", "manager"),
        assigned_to=payload.get("assigned_to", "frank.miller@acmeglobal.com"),
        priority=payload.get("priority", "MEDIUM"),
        sla_hours=float(payload.get("sla_hours", 24.0)),
        elapsed_hours=float(payload.get("elapsed_hours", 18.4)),
        status="IN_PROGRESS",
        department=payload.get("department", "Engineering"),
        requester_email=payload.get("requester_email", "alice.johnson@acmeglobal.com"),
        metadata=payload,
    )

    if session is not None and proc_id:
        try:
            proc_uuid = uuid.UUID(proc_id)
            stmt_p = select(ProcessInstance).where(ProcessInstance.id == proc_uuid)
            res_p = await session.execute(stmt_p)
            proc_row = res_p.scalar_one_or_none()

            if proc_row:
                ctx.process_title = proc_row.title
                ctx.process_type = proc_row.process_type
                ctx.department = proc_row.department or ctx.department
                ctx.status = proc_row.status

            if task_id:
                try:
                    task_uuid = uuid.UUID(task_id)
                    stmt_t = select(Task).where(Task.id == task_uuid)
                    res_t = await session.execute(stmt_t)
                    task_row = res_t.scalar_one_or_none()

                    if task_row:
                        ctx.task_title = task_row.title
                        ctx.task_type = task_row.task_type
                        ctx.assigned_role = task_row.assigned_role or ctx.assigned_role
                        ctx.assigned_to = task_row.assigned_to or ctx.assigned_to
                        ctx.priority = task_row.priority
                        ctx.sla_hours = task_row.sla_hours or 24.0

                        if task_row.started_at:
                            now = datetime.now(timezone.utc)
                            ctx.elapsed_hours = round(
                                (now - task_row.started_at).total_seconds() / 3600.0, 2
                            )
                except ValueError:
                    pass
        except ValueError:
            pass

    return ctx
