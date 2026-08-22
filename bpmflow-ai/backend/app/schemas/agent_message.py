"""Shared inter-agent message envelopes for BPMFlow AI.

Two shapes live here on purpose:
- AgentMessage / AgentMessageMetadata: Agent 3/4 routing envelope (nested metadata).
- DiscoveryAgentMessage: Agent 1 HTTP/discovery result (flat, informational only).

This is not the database agent_messages transport row.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1.0.0"

AGENT_1 = "agent1"
AGENT_2 = "agent2"
AGENT_3 = "agent3"
AGENT_4 = "agent4"


class AgentMessageType(str, Enum):
    """Shared message types. Agent 3 request/response values are included."""

    RESOURCE_ALLOCATION_REQUEST = "RESOURCE_ALLOCATION_REQUEST"
    RESOURCE_ALLOCATION_RESPONSE = "RESOURCE_ALLOCATION_RESPONSE"
    PROCESS_DISCOVERY_REQUEST = "PROCESS_DISCOVERY_REQUEST"
    PROCESS_DISCOVERY_RESPONSE = "PROCESS_DISCOVERY_RESPONSE"
    WORKFLOW_EXECUTION_REQUEST = "WORKFLOW_EXECUTION_REQUEST"
    WORKFLOW_EXECUTION_RESPONSE = "WORKFLOW_EXECUTION_RESPONSE"
    NOTIFICATION = "NOTIFICATION"
    ALERT = "ALERT"
    ERROR = "ERROR"


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def _require_timezone_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware (UTC)")
    return value


class AgentMessageMetadata(BaseModel):
    """Shared envelope metadata. correlation_id is the BPMFlow trace identifier."""

    message_id: UUID = Field(default_factory=uuid4)
    schema_version: str = Field(default=SCHEMA_VERSION, min_length=1)
    correlation_id: UUID
    process_instance_id: UUID
    task_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    sender: str = Field(min_length=1)
    receiver: str = Field(min_length=1)
    message_type: AgentMessageType
    timestamp: datetime = Field(default_factory=utc_now)

    @field_validator("timestamp", mode="after")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        return _require_timezone_aware(value, "timestamp")


class AgentMessage(BaseModel):
    """Generic inter-agent message. payload is agent-specific JSON data."""

    metadata: AgentMessageMetadata
    payload: Dict[str, Any] = Field(default_factory=dict)


AgentMessageStatus = Literal["COMPLETE", "PARTIAL", "NEEDS_CLARIFICATION"]


class EvidenceReference(BaseModel):
    """Pointer from a payload field back to source evidence."""

    model_config = ConfigDict(extra="forbid")

    field: str
    file_id: UUID
    page: Optional[int] = None
    span_start: Optional[int] = None
    span_end: Optional[int] = None


class DiscoveryAgentMessage(BaseModel):
    """Agent 1 discovery result. Informational only — no approve/decision fields."""

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

    def to_inter_agent_message(self, *, receiver: str = AGENT_4) -> AgentMessage:
        """Wrap this discovery result in the shared Agent 3/4 envelope."""
        return AgentMessage(
            metadata=AgentMessageMetadata(
                message_id=self.message_id,
                correlation_id=self.trace_id,
                process_instance_id=self.process_id,
                sender=AGENT_1,
                receiver=receiver,
                message_type=AgentMessageType.PROCESS_DISCOVERY_RESPONSE,
                timestamp=self.timestamp,
            ),
            payload=self.model_dump(mode="json"),
        )
