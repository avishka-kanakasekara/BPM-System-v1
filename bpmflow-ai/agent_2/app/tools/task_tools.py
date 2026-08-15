"""
Agent 2 — Task System Integration Tools (Mocked)

# MOCK: stands in for Agent 1/3 task-system integration; swap the body for a real call
when those agents exist — the signature and the guard/registry contract shouldn't need to change.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Task
from app.tools.schemas import (
    CreateTaskInput,
    CreateTaskOutput,
    UpdateTaskInput,
    UpdateTaskOutput,
)


async def create_workflow_task(
    session: Optional[AsyncSession], input_data: CreateTaskInput
) -> CreateTaskOutput:
    """
    # MOCK: Creates a new workflow task in the tasks table.
    """
    now = datetime.now(timezone.utc)
    task_uuid = uuid.uuid4()
    process_uuid = uuid.UUID(input_data.process_id)

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
    """
    # MOCK: Updates an existing workflow task status and assigned user.
    """
    now = datetime.now(timezone.utc)
    task_uuid = uuid.UUID(input_data.task_id)

    if session is not None:
        stmt = select(Task).where(Task.id == task_uuid)
        res = await session.execute(stmt)
        task_row = res.scalar_one_or_none()

        if task_row:
            task_row.status = input_data.status
            if input_data.assigned_to:
                task_row.assigned_to = input_data.assigned_to
            if input_data.result_notes:
                task_row.result_json = {"notes": input_data.result_notes}
            task_row.updated_at = now
            if input_data.status == "COMPLETED":
                task_row.completed_at = now
            await session.commit()

    return UpdateTaskOutput(
        task_id=str(task_uuid),
        status=input_data.status,
        updated_at=now.isoformat(),
    )
