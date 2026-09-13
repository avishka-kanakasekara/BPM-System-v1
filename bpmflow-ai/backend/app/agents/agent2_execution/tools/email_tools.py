"""
Agent 2 — Email Tool Wrappers
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.communication.schemas import EmailRequest
from app.agents.agent2_execution.tools.email_service import EmailService
from app.agents.agent2_execution.tools.schemas import (
    SendEmailInput,
    SendEmailOutput,
    SendReminderInput,
    SendReminderOutput,
)


def _recipient_list(primary: str, extra: list[str] | None) -> list[str]:
    values = [item.strip().lower() for item in ([primary, *(extra or [])]) if item and str(item).strip()]
    unique: list[str] = []
    for item in values:
        if item not in unique:
            unique.append(item)
    return unique


async def send_email_tool(
    session: AsyncSession | None, input_data: SendEmailInput
) -> SendEmailOutput:
    recipients = _recipient_list(input_data.recipient, input_data.recipients)
    service = EmailService(session=session, allowed_recipients=set(recipients))
    last_status = "FAILED"
    last_message_id = ""
    last_recipient = request_recipient_clean(input_data.recipient)
    for recipient in recipients:
        req = EmailRequest(
            recipient=recipient,
            subject=input_data.subject,
            body=input_data.body,
            priority="MEDIUM",
            process_id=input_data.process_id,
            task_id=input_data.task_id,
            recipient_role=input_data.recipient_role,
            template_name=input_data.template_name or "task_assignment.html",
        )
        res = await service.send_email(req)
        last_status = res.status
        last_message_id = res.message_id
        last_recipient = recipient
        if res.status == "FAILED":
            return SendEmailOutput(
                status=res.status,
                message_id=res.message_id,
                recipient=recipient,
            )
    return SendEmailOutput(
        status=last_status,
        message_id=last_message_id,
        recipient=last_recipient,
    )


async def send_reminder_tool(
    session: AsyncSession | None, input_data: SendReminderInput
) -> SendReminderOutput:
    recipients = _recipient_list(input_data.recipient, input_data.recipients)
    service = EmailService(session=session, allowed_recipients=set(recipients))
    last = None
    for recipient in recipients:
        req = EmailRequest(
            recipient=recipient,
            subject=f"Reminder: Task SLA Deadline ({input_data.elapsed_hours:.1f}h elapsed)",
            body=input_data.message or f"Task #{input_data.task_id} requires your attention.",
            priority="HIGH",
            process_id=input_data.process_id or "proc-system",
            task_id=input_data.task_id,
            recipient_role="manager",
            template_name="reminder.html",
        )
        last = await service.send_email(req)
        if last.status == "FAILED":
            break
    return SendReminderOutput(
        status=last.status if last is not None else "FAILED",
        task_id=input_data.task_id,
        notified_at=service.render_template(
            "reminder.html",
            {
                "subject": f"Reminder: Task SLA Deadline ({input_data.elapsed_hours:.1f}h elapsed)",
                "body": input_data.message or f"Task #{input_data.task_id} requires your attention.",
                "process_id": input_data.process_id or "proc-system",
                "task_id": input_data.task_id,
                "elapsed_hours": input_data.elapsed_hours,
                "sla_hours": input_data.sla_hours,
            },
        ),
    )


def request_recipient_clean(email: str) -> str:
    return email.strip().lower() if email else ""
