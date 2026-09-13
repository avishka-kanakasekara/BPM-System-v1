"""
Agent 2 — Email provider abstraction (Resend API + SMTP).

Never claims success before the provider confirms submission.
"""

from __future__ import annotations

import logging
import smtplib
import uuid
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.agents.agent2_execution.config import settings
from app.core.config import settings as core_settings
from app.core.http_client import async_client
from app.core.redaction import redact_text

logger = logging.getLogger("agent_2.tools.email_provider")


@dataclass
class EmailDispatchResult:
    success: bool
    status: str
    message_id: str
    provider: str
    external_reference: str
    error: str = ""


def email_dry_run_enabled() -> bool:
    return bool(settings.EMAIL_DRY_RUN)


def email_configured() -> bool:
    """Return True when live provider credentials are present (ignores dry-run flag)."""
    provider = (settings.EMAIL_PROVIDER or "smtp").strip().lower()
    if provider == "resend":
        return bool(settings.EMAIL_API_KEY and settings.EMAIL_FROM)
    return bool(settings.SMTP_HOST and settings.EMAIL_FROM)


def _from_address() -> str:
    return (settings.EMAIL_FROM or settings.SMTP_FROM_EMAIL or "").strip()


def _reply_to() -> str | None:
    value = (settings.EMAIL_REPLY_TO or "").strip()
    return value or None


async def dispatch_email(
    *,
    recipient: str,
    subject: str,
    body_plain: str,
    body_html: str,
    idempotency_key: str = "",
) -> EmailDispatchResult:
    """
    Send email via configured provider.

    DRY_RUN returns status DRY_RUN without contacting a provider.
    When not in dry-run and provider is unconfigured, returns FAILED.
    """
    if settings.EMAIL_DRY_RUN:
        msg_id = f"dry-{uuid.uuid4().hex[:12]}"
        logger.info(
            "email_dry_run",
            extra={
                "recipient": recipient,
                "subject": subject[:80],
                "idempotency_key": idempotency_key,
            },
        )
        return EmailDispatchResult(
            success=True,
            status="DRY_RUN",
            message_id=msg_id,
            provider="dry_run",
            external_reference=msg_id,
        )

    if not email_configured():
        return EmailDispatchResult(
            success=False,
            status="FAILED",
            message_id="",
            provider=(settings.EMAIL_PROVIDER or "smtp").lower(),
            external_reference="",
            error=(
                "Email provider is not configured. Set EMAIL_PROVIDER, EMAIL_API_KEY, "
                "EMAIL_FROM (Resend) or SMTP_HOST + EMAIL_FROM (SMTP)."
            ),
        )

    provider = (settings.EMAIL_PROVIDER or "smtp").strip().lower()
    if provider == "resend":
        return await _dispatch_resend(
            recipient=recipient,
            subject=subject,
            body_plain=body_plain,
            body_html=body_html,
            idempotency_key=idempotency_key,
        )
    return _dispatch_smtp(
        recipient=recipient,
        subject=subject,
        body_plain=body_plain,
        body_html=body_html,
    )


async def _dispatch_resend(
    *,
    recipient: str,
    subject: str,
    body_plain: str,
    body_html: str,
    idempotency_key: str,
) -> EmailDispatchResult:
    api_key = settings.EMAIL_API_KEY
    from_addr = _from_address()
    if not api_key or not from_addr:
        return EmailDispatchResult(
            success=False,
            status="FAILED",
            message_id="",
            provider="resend",
            error="Resend requires EMAIL_API_KEY and EMAIL_FROM",
        )

    payload: dict = {
        "from": from_addr,
        "to": [recipient],
        "subject": subject,
        "text": body_plain,
        "html": body_html,
    }
    reply_to = _reply_to()
    if reply_to:
        payload["reply_to"] = reply_to

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    try:
        async with async_client(timeout=core_settings.EXTERNAL_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers=headers,
            )
        if response.status_code >= 400:
            err_body = redact_text(response.text[:500])
            logger.error(
                "resend_send_failed",
                extra={"status": response.status_code, "body": err_body},
            )
            return EmailDispatchResult(
                success=False,
                status="FAILED",
                message_id="",
                provider="resend",
                error=f"Resend API error {response.status_code}: {err_body}",
            )
        data = response.json()
        ref = str(data.get("id") or "")
        msg_id = ref or f"resend-{uuid.uuid4().hex[:12]}"
        return EmailDispatchResult(
            success=True,
            status="ACCEPTED_BY_PROVIDER",
            message_id=msg_id,
            provider="resend",
            external_reference=ref or msg_id,
        )
    except Exception as exc:
        logger.exception("resend_dispatch_exception")
        return EmailDispatchResult(
            success=False,
            status="FAILED",
            message_id="",
            provider="resend",
            error=str(exc) or exc.__class__.__name__,
        )


def _dispatch_smtp(
    *,
    recipient: str,
    subject: str,
    body_plain: str,
    body_html: str,
) -> EmailDispatchResult:
    from_addr = _from_address()
    smtp_host = settings.SMTP_HOST or "localhost"
    smtp_port = settings.SMTP_PORT or 587

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr or "noreply@bpmflow-ai.com"
        msg["To"] = recipient
        reply_to = _reply_to()
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.attach(MIMEText(body_plain, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)

        msg_id = f"smtp-{uuid.uuid4().hex[:12]}"
        return EmailDispatchResult(
            success=True,
            status="ACCEPTED_BY_PROVIDER",
            message_id=msg_id,
            provider="smtp",
            external_reference=msg_id,
        )
    except Exception as exc:
        logger.exception("smtp_dispatch_failed")
        return EmailDispatchResult(
            success=False,
            status="FAILED",
            message_id="",
            provider="smtp",
            error=str(exc) or exc.__class__.__name__,
        )
