"""
Agent 2 — Tool Guard (Single Security Choke Point)

Enforces Non-Negotiable Rules #1, #2, #4, #6, #7:
1. Gemini NEVER executes anything directly — all function call proposals go through Tool Guard.
2. Every tool call passes through Tool Guard (allow-list + RBAC + parameter validation + recipient validation).
3. Hard-coded permission matrix (authorization.py) is enforced (Rule #4).
4. Email recipients are allow-listed against seeded org directory by role (Rule #6).
5. Every decision (allowed or blocked) gets an audit log entry (Rule #7).
"""

import json
import os
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.security import audit, authorization


class ToolGuardResult(BaseModel):
    """Result object returned by Tool Guard evaluation."""

    allowed: bool = Field(..., description="Whether tool execution is permitted")
    reason: str = Field(..., description="Explanation for allowed or blocked decision")
    tool_name: str = Field(..., description="Target tool identifier")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Validated parameters payload")
    error: str = Field(default="", description="Error details if blocked")


# ---------------------------------------------------------------------------
# Org Directory Email Allow-list Loader (Rule #6)
# ---------------------------------------------------------------------------

ORG_DIR_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "org_directory.json"
)

ALLOWED_EMAIL_ROLES: Set[str] = {
    "requester",
    "assigned_employee",
    "manager",
    "finance_officer",
    "procurement_officer",
    "escalation_contact",
}


def load_allowed_email_recipients() -> Set[str]:
    """
    Load allowed recipient email addresses from org_directory.json.
    Only emails associated with an allowed role are valid recipients.
    """
    allowed_emails = set()
    if os.path.exists(ORG_DIR_PATH):
        try:
            with open(ORG_DIR_PATH, "r") as f:
                data = json.load(f)
                for user in data.get("users", []):
                    role = user.get("role", "").strip().lower()
                    email = user.get("email", "").strip().lower()
                    if role in ALLOWED_EMAIL_ROLES and email:
                        allowed_emails.add(email)
        except Exception:
            pass
    return allowed_emails


class ToolGuard:
    """
    Central security choke point for tool invocation.
    """

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session
        self.allowed_emails = load_allowed_email_recipients()

    async def check(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        actor: str = "agent_2",
    ) -> ToolGuardResult:
        """
        Evaluate a proposed tool call against all security gates in sequence.

        :param tool_name: Target tool identifier
        :param parameters: Dict of arguments passed to tool
        :param actor: Identifier of calling actor
        :return: ToolGuardResult indicating allowed/blocked with detailed reason
        """
        if not tool_name:
            reason = "Tool name cannot be empty"
            await audit.log_audit_event(self.session, actor, "empty_tool", False, reason, payload=parameters)
            return ToolGuardResult(allowed=False, reason=reason, tool_name="", parameters=parameters, error="EMPTY_TOOL_NAME")

        tool_clean = tool_name.strip().lower()

        # Gate 1: Authorization Allow-list Check (Rule #4)
        if not authorization.is_permitted(tool_clean):
            reason = f"Action {tool_clean!r} is forbidden by Agent 2 security policy (Rule #4)"
            await audit.log_audit_event(self.session, actor, tool_clean, False, reason, payload=parameters)
            return ToolGuardResult(
                allowed=False,
                reason=reason,
                tool_name=tool_clean,
                parameters=parameters,
                error="FORBIDDEN_ACTION",
            )

        # Gate 2: Parameter Structure Validation
        param_error = self._validate_parameters(tool_clean, parameters)
        if param_error:
            reason = f"Parameter validation failed for {tool_clean!r}: {param_error}"
            await audit.log_audit_event(self.session, actor, tool_clean, False, reason, payload=parameters)
            return ToolGuardResult(
                allowed=False,
                reason=reason,
                tool_name=tool_clean,
                parameters=parameters,
                error="INVALID_PARAMETERS",
            )

        # Gate 3: Recipient Allow-list Validation for Email Tools (Rule #6)
        if tool_clean in ["send_email", "send_reminder", "schedule_reminder"]:
            recipient = parameters.get("recipient") or parameters.get("recipient_email") or ""
            recipient_clean = recipient.strip().lower()

            if not recipient_clean:
                reason = f"Email tool {tool_clean!r} requires a recipient address"
                await audit.log_audit_event(self.session, actor, tool_clean, False, reason, payload=parameters)
                return ToolGuardResult(
                    allowed=False,
                    reason=reason,
                    tool_name=tool_clean,
                    parameters=parameters,
                    error="MISSING_RECIPIENT",
                )

            # Check if recipient is in allowed org directory
            if self.allowed_emails and recipient_clean not in self.allowed_emails:
                reason = f"Recipient {recipient!r} is not in the allowed organizational directory by role (Rule #6)"
                await audit.log_audit_event(self.session, actor, tool_clean, False, reason, payload=parameters)
                return ToolGuardResult(
                    allowed=False,
                    reason=reason,
                    tool_name=tool_clean,
                    parameters=parameters,
                    error="RECIPIENT_NOT_ALLOWED",
                )

        # All security gates passed -> Allow tool call & write audit log
        reason = f"Tool call {tool_clean!r} authorized by Tool Guard"
        await audit.log_audit_event(self.session, actor, tool_clean, True, reason, payload=parameters)

        return ToolGuardResult(
            allowed=True,
            reason=reason,
            tool_name=tool_clean,
            parameters=parameters,
            error="",
        )

    def _validate_parameters(self, tool_name: str, params: Dict[str, Any]) -> str:
        """Helper to validate parameters per tool schema."""
        if not isinstance(params, dict):
            return "Parameters must be a dictionary"

        if tool_name in ["send_email", "send_reminder"]:
            if "subject" in params and not isinstance(params["subject"], str):
                return "Field 'subject' must be a string"
            if "body" in params and not isinstance(params["body"], str):
                return "Field 'body' must be a string"

        elif tool_name == "create_po_draft":
            if "vendor_id" not in params:
                return "Missing required field 'vendor_id'"
            if "amount" not in params:
                return "Missing required field 'amount'"
            if not isinstance(params["amount"], (int, float)) or params["amount"] <= 0:
                return "Field 'amount' must be a positive number"

        return ""
