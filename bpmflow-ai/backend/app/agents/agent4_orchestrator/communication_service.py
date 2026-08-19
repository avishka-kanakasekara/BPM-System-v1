"""Route shared AgentMessages to in-process agent adapters.

Does not change workflow stage, evaluate risk, or create approvals.
"""

from typing import Dict
from uuid import uuid4

from pydantic import ValidationError

from app.schemas.agent_message import (
    AGENT_1,
    AGENT_2,
    AGENT_3,
    AGENT_4,
    AgentMessage,
    AgentMessageMetadata,
    utc_now,
)

from .adapters import Agent1Adapter, Agent2Adapter, Agent3Adapter
from .communication import AgentAdapter
from .exceptions import (
    AgentUnavailableError,
    CommunicationFailureError,
    InvalidMessageError,
    UnsupportedAgentError,
)

KNOWN_AGENTS = frozenset({AGENT_1, AGENT_2, AGENT_3, AGENT_4})
ROUTABLE_RECEIVERS = frozenset({AGENT_1, AGENT_2, AGENT_3})


class AgentCommunicationService:
    """Validates and routes Agent 4 outbound messages."""

    def __init__(self, adapters: Dict[str, AgentAdapter] | None = None) -> None:
        self._adapters = adapters or {
            AGENT_1: Agent1Adapter(),
            AGENT_2: Agent2Adapter(),
            AGENT_3: Agent3Adapter(),
        }

    async def send(self, message: AgentMessage) -> AgentMessage:
        """Send a message to the adapter for message.metadata.receiver."""
        self._validate_message(message)
        receiver = message.metadata.receiver
        adapter = self._adapters.get(receiver)
        if adapter is None:
            raise UnsupportedAgentError(receiver)

        try:
            response = await adapter.send(message)
        except (AgentUnavailableError, UnsupportedAgentError, InvalidMessageError):
            raise
        except Exception as exc:
            raise CommunicationFailureError(
                f"Communication with {receiver} failed"
            ) from exc

        return self._finalize_response(message, response)

    def _validate_message(self, message: AgentMessage) -> None:
        if not isinstance(message, AgentMessage):
            raise InvalidMessageError("Expected a shared AgentMessage")
        try:
            AgentMessage.model_validate(message.model_dump())
        except ValidationError as exc:
            raise InvalidMessageError("Agent message failed validation") from exc

        sender = message.metadata.sender
        receiver = message.metadata.receiver
        if sender not in KNOWN_AGENTS:
            raise UnsupportedAgentError(sender)
        if receiver not in KNOWN_AGENTS:
            raise UnsupportedAgentError(receiver)
        if receiver not in ROUTABLE_RECEIVERS:
            raise UnsupportedAgentError(receiver)

    def _finalize_response(
        self,
        request: AgentMessage,
        response: AgentMessage,
    ) -> AgentMessage:
        if not isinstance(response, AgentMessage):
            raise CommunicationFailureError("Adapter did not return an AgentMessage")
        request_id = request.metadata.message_id
        response_id = response.metadata.message_id
        if response_id == request_id:
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
        )
