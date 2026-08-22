"""
Agent 2 — Scheduler & Escalation Tools

Schedules SLA reminders and escalations, persisting SLA events when a DB session exists.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.database.ids import parse_uuid
from app.agents.agent2_execution.database.models import SLAEvent
from app.agents.agent2_execution.database.persistence import ensure_task, record_workflow_event
from app.agents.agent2_execution.tools.schemas import ScheduleEscalationInput, ScheduleEscalationOutput, SendReminderOutput


async def schedule_reminder(
    session: Optional[AsyncSession],
    recipient: str,
    task_id: str,
    delay_hours: float = 4.0,
    message: str = "",
) -> SendReminderOutput:
    """Schedule a delayed reminder notification job."""
    now = datetime.now(timezone.utc)
    notified_at = now + timedelta(hours=delay_hours)
    await record_workflow_event(
        session,
        task_id,
        "REMINDER_SCHEDULED",
        task_id=task_id,
        metadata={"recipient": recipient, "message": message, "delay_hours": delay_hours},
        new_state="SCHEDULED",
    )
    return SendReminderOutput(
        status="SCHEDULED",
        task_id=task_id,
        notified_at=notified_at.isoformat(),
    )


async def schedule_escalation(
    session: Optional[AsyncSession], input_data: ScheduleEscalationInput
) -> ScheduleEscalationOutput:
    """Schedule a delayed escalation job for a task exceeding SLA threshold."""
    now = datetime.now(timezone.utc)
    scheduled_for = now + timedelta(minutes=input_data.delay_minutes)
    job_id = f"job-esc-{uuid.uuid4().hex[:8]}"

    if session is not None:
        await ensure_task(session, input_data.task_id, input_data.task_id, title="Escalation target")
        try:
            event = SLAEvent(
                id=uuid.uuid4(),
                task_id=parse_uuid(input_data.task_id),
                event_type="WARNING",
                sla_hours=max(1.0, input_data.delay_minutes / 60.0),
                elapsed_hours=0.0,
                threshold_percent=80.0,
                notified_roles={"escalation_role": input_data.escalation_role},
                message=f"Escalation scheduled for {input_data.escalation_role}",
            )
            session.add(event)
            await session.commit()
        except Exception:
            try:
                await session.rollback()
            except Exception:
                pass

    await record_workflow_event(
        session,
        input_data.task_id,
        "ESCALATION_SCHEDULED",
        task_id=input_data.task_id,
        metadata={
            "job_id": job_id,
            "escalation_role": input_data.escalation_role,
            "delay_minutes": input_data.delay_minutes,
            "scheduled_for": scheduled_for.isoformat(),
        },
        new_state="SCHEDULED",
    )

    return ScheduleEscalationOutput(
        job_id=job_id,
        status="SCHEDULED",
        scheduled_for=scheduled_for.isoformat(),
    )
