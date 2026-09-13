"""
Agent 2 — Email Service

Handles email validation (Rule #6 role allow-list), Jinja2 template rendering,
SMTP dispatch / dry-run logging, audit logging, and intelligent Gemini content drafting.
"""

import logging
import os
import uuid
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.communication.schemas import EmailRequest, EmailResult
from app.agents.agent2_execution.llm import prompts
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.security import audit
from app.agents.agent2_execution.security.tool_guard import load_allowed_email_recipients
from app.agents.agent2_execution.tools.email_provider import dispatch_email

logger = logging.getLogger("agent_2.tools.email_service")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# Jinja2 environment setup
jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


class IntelligentEmailDraft(BaseModel):
    subject: str = Field(..., description="Drafted email subject line")
    body: str = Field(..., description="Drafted semantic email text content")
    priority: str = Field(default="MEDIUM", description="Assessed priority: LOW, MEDIUM, HIGH, URGENT")


class EmailService:
    """
    Core Email Service managing recipient allow-listing, Jinja2 template rendering,
    SMTP dispatch / dry-run logging, and database tracking.
    """

    def __init__(self, session: AsyncSession | None = None):
        self.session = session
        self.allowed_recipients = load_allowed_email_recipients()

    def validate_recipient(self, email: str, recipient_role: str = "") -> tuple[bool, str]:
        """
        Enforce Rule #6 recipient allow-list validation.
        
        :param email: Target email address
        :param recipient_role: Optional recipient role
        :return: (is_valid, reason_message)
        """
        if not email:
            return False, "Recipient email address cannot be empty"

        email_clean = email.strip().lower()

        # If org directory is populated, recipient must be in directory
        if self.allowed_recipients and email_clean not in self.allowed_recipients:
            return (
                False,
                f"Recipient {email!r} is not in the allowed organizational directory by role (Rule #6)",
            )

        return True, "Recipient authorized"

    def render_template(self, template_name: str, context: dict[str, Any]) -> str:
        """
        Render a branded Jinja2 HTML email template.

        :param template_name: Name of template file (e.g. task_assignment.html)
        :param context: Template variable context dictionary
        :return: Rendered HTML string
        """
        template_file = template_name if template_name.endswith(".html") else f"{template_name}.html"
        try:
            template = jinja_env.get_template(template_file)
            return template.render(**context)
        except Exception as e:
            logger.error(f"Failed to render Jinja2 template {template_file}: {e}")
            # Fallback inline wrapper
            subject = context.get("subject", "Notification")
            body = context.get("body", "")
            return f"<html><body><h2>{subject}</h2><p>{body}</p></body></html>"

    async def send_email(self, request: EmailRequest) -> EmailResult:
        """
        Process and dispatch an email request.

        :param request: EmailRequest schema
        :return: EmailResult schema
        """
        # Step 1: Validate Recipient (Rule #6)
        is_valid, val_reason = self.validate_recipient(
            request.recipient, request.recipient_role
        )
        if not is_valid:
            await audit.log_audit_event(
                self.session,
                actor="email_service",
                action="send_email",
                allowed=False,
                reason=val_reason,
                payload=request.model_dump(),
            )
            return EmailResult(status="FAILED", message_id="", error=val_reason)

        # Step 2: Render Jinja2 Template
        template_name = request.template_name or "task_assignment.html"
        context = {
            "subject": request.subject,
            "body": request.body,
            "process_id": request.process_id,
            "task_id": request.task_id,
            "recipient_role": request.recipient_role,
            "priority": request.priority,
        }
        html_body = self.render_template(template_name, context)

        idempotency_key = f"{request.process_id}-{request.task_id}-send_email"
        dispatch = await dispatch_email(
            recipient=request.recipient,
            subject=request.subject,
            body_plain=request.body,
            body_html=html_body,
            idempotency_key=idempotency_key,
        )
        message_id = dispatch.message_id or f"msg-{uuid.uuid4().hex[:12]}"
        status_result = dispatch.status
        error_msg = dispatch.error

        # Step 4: Audit Log
        # NOTE: EmailEvent requires a valid execution_receipt_id foreign key. Tool handlers
        # in this repo currently do not pass receipt IDs into EmailService, so writing a fake
        # UUID here would break referential integrity on a real database. Keep the action
        # audited and return a tool result without creating an invalid row.

        await audit.log_audit_event(
            self.session,
            actor="email_service",
            action="send_email",
            allowed=(status_result != "FAILED"),
            reason=f"Email dispatch completed with status {status_result}",
            payload={"recipient": request.recipient, "message_id": message_id},
        )

        if status_result == "SENT":
            status_result = "ACCEPTED_BY_PROVIDER"
        return EmailResult(status=status_result, message_id=message_id, error=error_msg)

    async def draft_intelligent_email(
        self, context: dict[str, Any], gemini_client: GeminiClient | None = None
    ) -> IntelligentEmailDraft:
        """
        Use Gemini to draft intelligent email subject, body, and priority based on process context.

        :param context: Dict containing recipient_role, purpose, process_id, current_state, etc.
        :param gemini_client: Optional GeminiClient instance
        :return: IntelligentEmailDraft object
        """
        client = gemini_client or GeminiClient()
        prompt_text = (
            f"Draft a notification email for recipient role '{context.get('recipient_role', 'manager')}'.\n"
            f"Purpose: {context.get('purpose', 'SLA Reminder')}\n"
            f"Process ID: {context.get('process_id', '')}\n"
            f"Task ID: {context.get('task_id', '')}\n"
            f"Process title: {context.get('process_title', '')}\n"
            f"Task title: {context.get('task_title', '')}\n"
            f"Current State: {context.get('current_state', 'IN_PROGRESS')}\n"
            f"Elapsed Hours: {context.get('elapsed_hours', 0.0)} / SLA: {context.get('sla_hours', 24.0)} hours.\n"
            f"Assigned to: {context.get('assigned_to', '')}\n"
            "Do not invent names, vendors, or purchase amounts that are not in this context."
        )

        draft = await client.generate_structured_output(
            prompt=prompt_text,
            response_schema=IntelligentEmailDraft,
            system_instruction=prompts.SYSTEM_PROMPT_EMAIL_DRAFTING,
            model_tier="flash",
        )
        return draft

