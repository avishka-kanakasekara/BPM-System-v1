"""Shared inter-agent message envelope for BPMFlow AI.

Preserves Agent 3 metadata field names and meanings. Agent-specific payloads
(e.g. AllocationRequest / AllocationRecommendation) stay in agent packages.
This is not the database agent_messages transport row.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

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
