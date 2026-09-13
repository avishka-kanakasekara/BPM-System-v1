"""Unified email service entry point (transport + orchestration).

Import from here instead of agent2 tool modules directly.
"""

from app.agents.agent2_execution.tools.email_provider import (
    EmailDispatchResult,
    dispatch_email,
    email_configured,
    email_dry_run_enabled,
)
from app.agents.agent2_execution.tools.email_service import EmailService, IntelligentEmailDraft

__all__ = [
    "EmailDispatchResult",
    "EmailService",
    "IntelligentEmailDraft",
    "dispatch_email",
    "email_configured",
    "email_dry_run_enabled",
]
