"""Shared Agent-to-Agent message envelope.

Agent 1 only informs. This schema must not grow approve/decision/authorization fields.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


AgentMessageStatus = Literal["COMPLETE", "PARTIAL", "NEEDS_CLARIFICATION"]


class EvidenceReference(BaseModel):
    """Pointer from a payload field back to source evidence."""

    model_config = ConfigDict(extra="forbid")

    field: str
    file_id: UUID
    page: Optional[int] = None
    span_start: Optional[int] = None
    span_end: Optional[int] = None


class AgentMessage(BaseModel):
    """Envelope used by all four agents. Informational only — no decisions."""

    model_config = ConfigDict(extra="forbid")

    message_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID = Field(default_factory=uuid4)
    process_id: UUID = Field(default_factory=uuid4)
    sender: str = "agent1_discovery"
    timestamp: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_references: list[EvidenceReference] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    status: AgentMessageStatus
