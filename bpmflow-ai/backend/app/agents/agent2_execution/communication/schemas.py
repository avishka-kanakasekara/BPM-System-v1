"""
Agent 2 — Communication Schemas (Pydantic v2)

Defines data contracts for email dispatch, notifications, and communication tasks.

Rule #6 invariant: Email recipients are allow-listed by role (requester, assigned employee, manager, finance officer, procurement officer, authorized escalation recipient).
"""

from typing import Literal
from pydantic import BaseModel, Field

# Re-export AgentMessage from app.agents.agent2_execution.llm.schemas for communication contracts
from app.agents.agent2_execution.llm.schemas import AgentMessage


class EmailRequest(BaseModel):
    """
    Represents an outbound email dispatch request.

    Produced by: Communication Subsystem / Notification Engine during ACT phase.
    Operational role: Subject to Rule #6 role allow-list verification prior to dispatch.
    """

    recipient: str = Field(..., description="Recipient email address (must match role allow-list)")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Email body content (text or rendered HTML)")
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] = Field(default="MEDIUM", description="Email dispatch priority")
    process_id: str = Field(..., description="Associated process instance ID")
    task_id: str = Field(..., description="Associated task ID")
    recipient_role: str = Field(default="requester", description="Role of the recipient (e.g. requester, manager, finance_officer)")
    template_name: str = Field(default="", description="Optional Jinja2 email template name")


class EmailResult(BaseModel):
    """
    Represents the result of an email dispatch operation.

    Produced by: Email Service (SMTP provider / dry-run handler).
    Operational role: Passed back to Tool Guard and recorded in execution receipts & email_events table.
    """

    status: Literal["SENT", "DRY_RUN", "FAILED", "QUEUED"] = Field(..., description="Status of email dispatch")
    message_id: str = Field(default="", description="Unique email message identifier or provider ID")
    error: str = Field(default="", description="Detailed error description if dispatch failed")
