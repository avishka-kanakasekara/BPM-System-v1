"""
Agent 2 — Email Tool Wrappers

Provides registered tool entry points calling EmailService under the hood:
- send_email (task_assignment.html / default)
- send_reminder (reminder.html)
- send_escalation (escalation.html)
- send_task_assignment (task_assignment.html)
- send_exception_notification (exception.html)
- send_approval_notification (sla_warning.html / approval)
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.schemas import EmailRequest, EmailResult
from app.tools.email_service import EmailService
from app.tools.schemas import (
    SendEmailInput,
    SendEmailOutput,
    SendReminderInput,
    SendReminderOutput,
)


async def send_email_tool(
    session: Optional[AsyncSession], input_data: SendEmailInput
) -> SendEmailOutput:
    """Send an outbound role email using EmailService."""
    service = EmailService(session=session)
    req = EmailRequest(
        recipient=input_data.recipient,
        subject=input_data.subject,
        body=input_data.body,
        priority="MEDIUM",
        process_id=input_data.process_id,
        task_id=input_data.task_id,
        recipient_role=input_data.recipient_role,
        template_name=input_data.template_name or "task_assignment.html",
    )
    res = await service.send_email(req)
    return SendEmailOutput(
        status=res.status,
        message_id=res.message_id,
        recipient=request_recipient_clean(input_data.recipient),
    )


async def send_reminder_tool(
    session: Optional[AsyncSession], input_data: SendReminderInput
) -> SendReminderOutput:
    """Send an SLA reminder email using EmailService."""
    service = EmailService(session=session)
    req = EmailRequest(
        recipient=input_data.recipient,
        subject=f"Reminder: Task SLA Deadline ({input_data.elapsed_hours:.1f}h elapsed)",
        body=input_data.message or f"Task #{input_data.task_id} requires your attention.",
        priority="HIGH",
        process_id="proc-system",
        task_id=input_data.task_id,
        recipient_role="manager",
        template_name="reminder.html",
    )
    res = await service.send_email(req)
    return SendReminderOutput(
        status=res.status,
        task_id=input_data.task_id,
        notified_at=service.render_template("reminder.html", {"subject": req.subject, "body": req.body, "process_id": req.process_id, "task_id": req.task_id, "elapsed_hours": input_data.elapsed_hours, "sla_hours": input_data.sla_hours}),
    )


def request_recipient_clean(email: str) -> str:
    return email.strip().lower() if email else ""
