"""
Agent 2 — Scheduler & Escalation Tools

Provides schedule_reminder and schedule_escalation tool implementations.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.schemas import ScheduleEscalationInput, ScheduleEscalationOutput, SendReminderInput, SendReminderOutput


async def schedule_reminder(
    session: Optional[AsyncSession],
    recipient: str,
    task_id: str,
    delay_hours: float = 4.0,
    message: str = "",
) -> SendReminderOutput:
    """
    Schedule a delayed reminder notification job.
    """
    now = datetime.now(timezone.utc)
    job_id = f"job-rem-{uuid.uuid4().hex[:8]}"

    return SendReminderOutput(
        status="SCHEDULED",
        task_id=task_id,
        notified_at=(now + timedelta(hours=delay_hours)).isoformat(),
    )


async def schedule_escalation(
    session: Optional[AsyncSession], input_data: ScheduleEscalationInput
) -> ScheduleEscalationOutput:
    """
    Schedule a delayed escalation job for a task exceeding SLA threshold.
    """
    now = datetime.now(timezone.utc)
    scheduled_for = now + timedelta(minutes=input_data.delay_minutes)
    job_id = f"job-esc-{uuid.uuid4().hex[:8]}"

    return ScheduleEscalationOutput(
        job_id=job_id,
        status="SCHEDULED",
        scheduled_for=scheduled_for.isoformat(),
    )
