"""
Agent 2 — Email Service

Handles email validation (Rule #6 role allow-list), Jinja2 template rendering,
SMTP dispatch / dry-run logging, audit logging, and intelligent Gemini content drafting.
"""

import logging
import os
import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.schemas import EmailRequest, EmailResult
from app.config import settings
from app.database.models import EmailEvent
from app.llm import prompts
from app.llm.gemini_client import GeminiClient
from app.security import audit
from app.security.tool_guard import load_allowed_email_recipients

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

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session
        self.allowed_recipients = load_allowed_email_recipients()

    def validate_recipient(self, email: str, recipient_role: str = "") -> Tuple[bool, str]:
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

    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
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

        message_id = f"msg-{uuid.uuid4().hex[:12]}"
        status_result = "DRY_RUN" if settings.EMAIL_DRY_RUN else "SENT"
        error_msg = ""

        # Step 3: SMTP Dispatch or Dry-Run Logging
        if settings.EMAIL_DRY_RUN:
            logger.info(
                f"[EMAIL DRY RUN] To: {request.recipient} | Subject: {request.subject!r} | Template: {template_name}"
            )
        else:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = request.subject
                msg["From"] = settings.SMTP_FROM_EMAIL or "noreply@bpmflow-ai.com"
                msg["To"] = request.recipient
                msg.attach(MIMEText(request.body, "plain"))
                msg.attach(MIMEText(html_body, "html"))

                smtp_host = settings.SMTP_HOST or "localhost"
                smtp_port = settings.SMTP_PORT or 587

                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                    if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                        server.starttls()
                        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                    server.send_message(msg)

                status_result = "SENT"
            except Exception as e:
                logger.error(f"SMTP dispatch failed: {e}")
                status_result = "FAILED"
                error_msg = str(e)

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

        return EmailResult(status=status_result, message_id=message_id, error=error_msg)

    async def draft_intelligent_email(
        self, context: Dict[str, Any], gemini_client: Optional[GeminiClient] = None
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

    def retry(self, request: EmailRequest):
        """
        # TODO: Reference Prompt 8 Retry Manager — retry logic managed centrally in execution engine.
        """
        pass
