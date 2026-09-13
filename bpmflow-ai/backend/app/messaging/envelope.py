"""Factory helpers for shared inter-agent message envelopes."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.schemas.agent_message import (
    SCHEMA_VERSION,
    AgentMessage,
    AgentMessageMetadata,
    AgentMessageType,
    utc_now,
)


def build_agent_message(
    *,
    sender: str,
    receiver: str,
    message_type: AgentMessageType,
    process_instance_id: UUID,
    correlation_id: UUID,
    payload: dict[str, Any] | None = None,
    task_id: UUID | None = None,
    tenant_id: UUID | None = None,
    status: str | None = None,
    confidence: float | None = None,
    evidence_refs: list[str] | None = None,
    message_id: UUID | None = None,
) -> AgentMessage:
    """Create a validated outbound AgentMessage envelope."""
    return AgentMessage(
        metadata=AgentMessageMetadata(
            message_id=message_id or uuid4(),
            schema_version=SCHEMA_VERSION,
            correlation_id=correlation_id,
            process_instance_id=process_instance_id,
            task_id=task_id,
            tenant_id=tenant_id,
            sender=sender,
            receiver=receiver,
            message_type=message_type,
            timestamp=utc_now(),
        ),
        payload=payload or {},
        status=status,
        confidence=confidence,
        evidence_refs=evidence_refs or [],
    )


def build_response_envelope(
    request: AgentMessage,
    response: AgentMessage,
) -> AgentMessage:
    """Swap sender/receiver and preserve correlation for an adapter reply."""
    response_id = response.metadata.message_id
    if response_id == request.metadata.message_id:
        response_id = uuid4()
    return AgentMessage(
        metadata=AgentMessageMetadata(
            message_id=response_id,
            schema_version=response.metadata.schema_version,
            correlation_id=request.metadata.correlation_id,
            process_instance_id=request.metadata.process_instance_id,
            task_id=request.metadata.task_id,
            tenant_id=request.metadata.tenant_id,
            sender=request.metadata.receiver,
            receiver=request.metadata.sender,
            message_type=response.metadata.message_type,
            timestamp=utc_now(),
        ),
        payload=response.payload,
        status=response.status,
        confidence=response.confidence,
        evidence_refs=response.evidence_refs,
    )
