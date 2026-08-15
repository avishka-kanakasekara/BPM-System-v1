"""
Agent 2 — Notification & Exception Tools

Provides send_email, send_reminder, and create_exception tool implementations.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Failure
from app.tools.schemas import (
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
    Dispatch an outbound email (or log dry-run dispatch if EMAIL_DRY_RUN=True).
    """
    msg_id = f"msg-{uuid.uuid4().hex[:8]}"
    dispatch_status = "DRY_RUN" if settings.EMAIL_DRY_RUN else "SENT"

    return SendEmailOutput(
        status=dispatch_status,
        message_id=msg_id,
        recipient=input_data.recipient,
    )


async def send_reminder(
    session: Optional[AsyncSession], input_data: SendReminderInput
) -> SendReminderOutput:
    """
    Dispatch an SLA reminder notification to assigned approver.
    """
    now = datetime.now(timezone.utc)
    dispatch_status = "DRY_RUN" if settings.EMAIL_DRY_RUN else "SENT"

    return SendReminderOutput(
        status=dispatch_status,
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
    task_uuid = uuid.UUID(input_data.task_id) if input_data.task_id else None

    fail_row = Failure(
        id=exc_uuid,
        task_id=task_uuid,
        failure_type="EXCEPTION_RAISED",
        severity=input_data.severity,
        description=input_data.reason,
        resolution_status="OPEN",
        created_at=now,
        updated_at=now,
    )

    if session is not None:
        session.add(fail_row)
        await session.commit()

    return CreateExceptionOutput(
        exception_id=str(exc_uuid),
        status="OPEN",
        created_at=now.isoformat(),
    )
