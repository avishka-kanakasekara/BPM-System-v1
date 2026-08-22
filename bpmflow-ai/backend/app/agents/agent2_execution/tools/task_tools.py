"""
Agent 2 — Task System Integration Tools

Persists workflow tasks to the shared canonical `tasks` table used by all
agents (Agent 1 discovery steps, Agent 4 approvals FK, Agent 2 execution).
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.database.ids import parse_uuid
from app.agents.agent2_execution.database.models import Task
from app.agents.agent2_execution.database.persistence import ensure_process_instance
from app.agents.agent2_execution.tools.schemas import (
    CreateTaskInput,
    CreateTaskOutput,
    UpdateTaskInput,
    UpdateTaskOutput,
)


async def create_workflow_task(
    session: Optional[AsyncSession], input_data: CreateTaskInput
) -> CreateTaskOutput:
    """Create a new workflow task and persist it when a DB session is available."""
    now = datetime.now(timezone.utc)
    task_uuid = uuid.uuid4()
    process_uuid = parse_uuid(input_data.process_id)

    await ensure_process_instance(
        session,
        input_data.process_id,
        title=input_data.title,
        process_type="procurement",
    )

    task_row = Task(
        id=task_uuid,
        process_instance_id=process_uuid,
        title=input_data.title,
        description=input_data.description,
        task_type=input_data.task_type,
        status="PENDING",
        assigned_role=input_data.assigned_role,
        sla_hours=input_data.sla_hours,
        priority=input_data.priority,
        created_at=now,
        updated_at=now,
    )

    if session is not None:
        session.add(task_row)
        await session.commit()

    return CreateTaskOutput(
        task_id=str(task_uuid),
        status="PENDING",
        created_at=now.isoformat(),
    )


async def update_task(
    session: Optional[AsyncSession], input_data: UpdateTaskInput
) -> UpdateTaskOutput:
    """Update an existing workflow task status and assigned user."""
    now = datetime.now(timezone.utc)
    task_uuid = parse_uuid(input_data.task_id)

    if session is not None:
        stmt = select(Task).where(Task.id == task_uuid)
        res = await session.execute(stmt)
        task_row = res.scalar_one_or_none()

        if task_row:
            task_row.status = input_data.status
            if input_data.assigned_to:
                task_row.assigned_to_email = input_data.assigned_to
            if input_data.result_notes:
                task_row.result_json = {"notes": input_data.result_notes}
            task_row.updated_at = now
            if input_data.status == "IN_PROGRESS" and not task_row.started_at:
                task_row.started_at = now
            if input_data.status == "COMPLETED":
                task_row.completed_at = now
            await session.commit()

    return UpdateTaskOutput(
        task_id=str(task_uuid),
        status=input_data.status,
        updated_at=now.isoformat(),
    )
