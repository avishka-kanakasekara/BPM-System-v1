"""
Agent 2 — Tool Guard (Single Security Choke Point)

Enforces Non-Negotiable Rules #1, #2, #4, #6, #7:
1. Gemini NEVER executes anything directly — all function call proposals go through Tool Guard.
2. Every tool call passes through Tool Guard (allow-list + RBAC + parameter validation + recipient validation).
3. Hard-coded permission matrix (authorization.py) is enforced (Rule #4).
4. Email recipients must be verified tenant-scoped Company Directory employees (Rule #6).
5. Every decision (allowed or blocked) gets an audit log entry (Rule #7).
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.security import audit, authorization
from app.company_directory.communication import resolve_verified_recipient_emails
from app.company_directory.exceptions import DirectoryError
from app.company_directory.service import CompanyDirectoryService


@dataclass(frozen=True)
class ExecutionGuardContext:
    """Server-side execution authorization context for Tool Guard."""

    message_status: str = "AUTHORIZED"
    process_stage: str = "WORKFLOW_EXECUTION"
    is_retry: bool = False
    process_id: str = ""
    tenant_id: str = ""
    workflow_plan_id: str = ""
    workflow_step_id: str = ""


class ToolGuardResult(BaseModel):
    """Result object returned by Tool Guard evaluation."""

    allowed: bool = Field(..., description="Whether tool execution is permitted")
    reason: str = Field(..., description="Explanation for allowed or blocked decision")
    tool_name: str = Field(..., description="Target tool identifier")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Validated parameters payload")
    error: str = Field(default="", description="Error details if blocked")


class ToolGuard:
    """
    Central security choke point for tool invocation.
    """

    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        directory: CompanyDirectoryService | None = None,
    ):
        self.session = session
        self.directory = directory

    async def check(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        actor: str = "agent_2",
        guard_context: ExecutionGuardContext | None = None,
    ) -> ToolGuardResult:
        if not tool_name:
            reason = "Tool name cannot be empty"
            await audit.log_audit_event(self.session, actor, "empty_tool", False, reason, payload=parameters)
            return ToolGuardResult(allowed=False, reason=reason, tool_name="", parameters=parameters, error="EMPTY_TOOL_NAME")

        tool_clean = tool_name.strip().lower()
        ctx = guard_context or ExecutionGuardContext()

        if ctx.message_status and ctx.message_status != "AUTHORIZED":
            reason = (
                f"Tool call rejected: message status must be AUTHORIZED "
                f"(got {ctx.message_status!r})"
            )
            await audit.log_audit_event(self.session, actor, tool_clean, False, reason, payload=parameters)
            return ToolGuardResult(
                allowed=False,
                reason=reason,
                tool_name=tool_clean,
                parameters=parameters,
                error="NOT_AUTHORIZED",
            )

        from app.agents.agent2_execution.tools.metadata import READ_ONLY_TOOLS

        if tool_clean not in READ_ONLY_TOOLS:
            stage = (ctx.process_stage or "").upper()
            if stage != "WORKFLOW_EXECUTION":
                reason = (
                    f"Tool {tool_clean!r} requires WORKFLOW_EXECUTION stage "
                    f"(current: {stage or 'UNKNOWN'})"
                )
                await audit.log_audit_event(self.session, actor, tool_clean, False, reason, payload=parameters)
                return ToolGuardResult(
                    allowed=False,
                    reason=reason,
                    tool_name=tool_clean,
                    parameters=parameters,
                    error="STAGE_NOT_AUTHORIZED",
                )

        if tool_clean in READ_ONLY_TOOLS:
            process_id = str(parameters.get("process_id") or ctx.process_id or "").strip()
            if not process_id:
                reason = f"Read-only tool {tool_clean!r} requires a valid process_id"
                await audit.log_audit_event(self.session, actor, tool_clean, False, reason, payload=parameters)
                return ToolGuardResult(
                    allowed=False,
                    reason=reason,
                    tool_name=tool_clean,
                    parameters=parameters,
                    error="MISSING_PROCESS_ID",
                )

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

        if tool_clean in ["send_email", "send_reminder", "schedule_reminder"]:
            recipient_error = self._validate_directory_recipients(parameters, ctx)
            if recipient_error:
                code, reason = recipient_error
                await audit.log_audit_event(self.session, actor, tool_clean, False, reason, payload=parameters)
                return ToolGuardResult(
                    allowed=False,
                    reason=reason,
                    tool_name=tool_clean,
                    parameters=parameters,
                    error=code,
                )

        reason = f"Tool call {tool_clean!r} authorized by Tool Guard"
        await audit.log_audit_event(self.session, actor, tool_clean, True, reason, payload=parameters)

        return ToolGuardResult(
            allowed=True,
            reason=reason,
            tool_name=tool_clean,
            parameters=parameters,
            error="",
        )

    def _validate_directory_recipients(
        self,
        parameters: dict[str, Any],
        ctx: ExecutionGuardContext,
    ) -> tuple[str, str] | None:
        raw_ids = parameters.get("recipient_employee_ids") or []
        tenant_raw = parameters.get("tenant_id") or ctx.tenant_id
        if not raw_ids:
            recipient = str(parameters.get("recipient") or parameters.get("recipient_email") or "").strip()
            if not recipient:
                return (
                    "MISSING_RECIPIENT",
                    f"Email tool requires a recipient address",
                )
            if self.directory is not None:
                return (
                    "COMMUNICATION_RECIPIENT_INVALID",
                    "Email tools require recipient_employee_ids from the WorkflowStep",
                )
            return None
        if not tenant_raw:
            return (
                "COMMUNICATION_RECIPIENT_INVALID",
                "Authenticated tenant is required before email execution",
            )
        if self.directory is None:
            return (
                "COMPANY_DIRECTORY_UNAVAILABLE",
                "Company directory is required to validate email recipients",
            )
        try:
            tenant_id = tenant_raw if isinstance(tenant_raw, UUID) else UUID(str(tenant_raw))
            employee_ids = [
                item if isinstance(item, UUID) else UUID(str(item)) for item in raw_ids
            ]
            verified = resolve_verified_recipient_emails(
                tenant_id=tenant_id,
                employee_ids=employee_ids,
                directory=self.directory,
                workflow_plan_id=_uuid_or_none(ctx.workflow_plan_id or parameters.get("workflow_plan_id")),
                workflow_step_id=_uuid_or_none(ctx.workflow_step_id or parameters.get("workflow_step_id")),
                process_id=_uuid_or_none(parameters.get("process_id") or ctx.process_id),
            )
        except DirectoryError as exc:
            return exc.error_code, str(exc)
        except (TypeError, ValueError):
            return (
                "COMMUNICATION_RECIPIENT_INVALID",
                "recipient_employee_ids must be valid employee UUIDs",
            )

        supplied = []
        if parameters.get("recipients"):
            supplied = [str(item).strip().lower() for item in parameters.get("recipients") or []]
        elif parameters.get("recipient") or parameters.get("recipient_email"):
            supplied = [str(parameters.get("recipient") or parameters.get("recipient_email")).strip().lower()]
        if not supplied:
            return (
                "MISSING_RECIPIENT",
                "Email tool requires a recipient address resolved from Company Directory",
            )
        verified_set = {item.strip().lower() for item in verified}
        if any(item not in verified_set for item in supplied):
            return (
                "RECIPIENT_NOT_ALLOWED",
                "Recipient is not a verified Company Directory employee email (Rule #6)",
            )
        if len(supplied) != len(verified):
            return (
                "COMMUNICATION_RECIPIENT_INVALID",
                "Every recipient_employee_id must be resolved; partial send is not allowed",
            )
        return None

    def _validate_parameters(self, tool_name: str, params: dict[str, Any]) -> str:
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


def _uuid_or_none(value: Any) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        return None
