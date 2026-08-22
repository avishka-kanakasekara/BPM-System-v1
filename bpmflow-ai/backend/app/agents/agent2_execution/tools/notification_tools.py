"""
Agent 2 — Notification & Exception Tools

Provides send_email, send_reminder, and create_exception tool implementations.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.communication.schemas import EmailRequest
from app.agents.agent2_execution.database.ids import parse_uuid
from app.agents.agent2_execution.database.models import Failure
from app.agents.agent2_execution.database.persistence import ensure_process_instance, ensure_task
from app.agents.agent2_execution.tools.email_service import EmailService
from app.agents.agent2_execution.tools.schemas import (
    CreateExceptionInput,
    CreateExceptionOutput,
    SendEmailInput,
    SendEmailOutput,
    SendReminderInput,
    SendReminderOutput,
)


async def send_email(
    session: Optional[AsyncSession], input_data: SendEmailInput
) -> SendEmailOutput:
    """
    Dispatch an outbound email through EmailService.
    """
    service = EmailService(session=session)
    result = await service.send_email(
        EmailRequest(
            recipient=input_data.recipient,
            subject=input_data.subject,
            body=input_data.body,
            process_id=input_data.process_id,
            task_id=input_data.task_id,
            recipient_role=input_data.recipient_role,
            template_name=input_data.template_name or "task_assignment.html",
        )
    )

    return SendEmailOutput(
        status=result.status,
        message_id=result.message_id,
        recipient=input_data.recipient,
    )


async def send_reminder(
    session: Optional[AsyncSession], input_data: SendReminderInput
) -> SendReminderOutput:
    """
    Dispatch an SLA reminder notification through EmailService.
    """
    now = datetime.now(timezone.utc)
    service = EmailService(session=session)
    subject = f"SLA Reminder: Task {input_data.task_id} needs attention"
    body = input_data.message or (
        f"Task {input_data.task_id} has been open for {input_data.elapsed_hours:.1f} hours "
        f"against an SLA of {input_data.sla_hours:.1f} hours."
    )
    result = await service.send_email(
        EmailRequest(
            recipient=input_data.recipient,
            subject=subject,
            body=body,
            priority="HIGH",
            process_id=getattr(input_data, "process_id", "") or "",
            task_id=input_data.task_id,
            recipient_role="manager",
            template_name="reminder.html",
        )
    )

    return SendReminderOutput(
        status=result.status,
        task_id=input_data.task_id,
        notified_at=now.isoformat(),
    )


async def create_exception(
    session: Optional[AsyncSession], input_data: CreateExceptionInput
) -> CreateExceptionOutput:
    """
    Raise an exception ticket for human supervisor intervention.
    """
    now = datetime.now(timezone.utc)
    exc_uuid = uuid.uuid4()
    fail_row = Failure(
        id=exc_uuid,
        task_id=parse_uuid(input_data.task_id) if input_data.task_id else None,
        failure_type="EXCEPTION_RAISED",
        severity=input_data.severity,
        description=input_data.reason,
        resolution_status="OPEN",
        created_at=now,
        updated_at=now,
    )

    if session is not None:
        try:
            await ensure_process_instance(session, input_data.process_id)
            await ensure_task(session, input_data.process_id, input_data.task_id)
            session.add(fail_row)
            await session.commit()
        except Exception:
            try:
                await session.rollback()
            except Exception:
                pass

    return CreateExceptionOutput(
        exception_id=str(exc_uuid),
        status="OPEN",
        created_at=now.isoformat(),
    )
